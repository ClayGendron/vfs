"""The row-label grants spike: build the world, label it, time the shapes, check recall.

Two modes:

    uv run --no-sync python bench.py --engine sqlite --n 10000
    uv run --no-sync python bench.py --engine postgres --n 10000
    uv run --no-sync python bench.py --engine sqlite --writes      # relabel and move costs

The read mode (``--n``) loads the world at N users, computes every
caller's truth set in Python from the spec's rules, times the compile
and the statement shapes for both labelling variants (cold = a fresh
connection, warm = median of ``--reps`` runs), checks every answer
against the truth, prints the plans, measures the indexes, and writes
``runs/<engine>-<N>.md``. The write mode builds a 1,000-row, a
10,000-row and a 1,000,000-row folder beside a 1,000-user world and
times the relabel a posture change, a new grant boundary and a move
cost, checking the labels afterwards against the Python labeller.

Postgres is shared with another agent: every table is prefixed with
``rl_<hex>_`` and dropped at the end. Study code only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pickle
import random
import sqlite3
import statistics
import time
from typing import Any
from uuid import uuid4

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from prototype import (
    NEXT,
    Caller,
    Dialect,
    Domains,
    Names,
    Pieces,
    Span,
    ancestors_and_self,
    compile_rights,
    ddl,
    domain_list_sql,
    index_ddl,
    labels,
    names,
    public_level,
    relabel_spans,
    split,
    statements,
    truth,
    visible_sql,
)
from vfs.storage.grants import GrantRow, resolve
from world import HEAVY_GROUP, NONE, READ, READ_WRITE, World, build, callers

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH = os.environ.get("RL_SCRATCH", "/Users/claygendron/.claude/jobs/b627c391/tmp/research/rowlabel")
PG_URL = os.environ.get("RL_PG_URL", "postgresql+asyncpg://vfs:vfs@localhost:54320/vfs")
PG_JIT_OFF = os.environ.get("RL_PG_JIT_OFF") == "1"  # probe: Postgres with JIT disabled per session
RUN_SUFFIX = "-jitoff" if PG_JIT_OFF else ""
VARIANTS = ("public", "domain")
STATEMENTS = ("entries", "scoped", "count", "top10", "top10 probe")
SQLITE_PRAGMAS = (
    "PRAGMA busy_timeout = 5000",
    "PRAGMA synchronous = FULL",
    "PRAGMA case_sensitive_like = ON",
    "PRAGMA mmap_size = 8589934592",
    "PRAGMA cache_size = -262144",
)
LEVEL_NAME = {0: "none", 1: "read", 2: "read_write"}


# ---------------------------------------------------------------------------
# Engines and loading
# ---------------------------------------------------------------------------


def sqlite_path(tag: str) -> str:
    os.makedirs(SCRATCH, exist_ok=True)
    return os.path.join(SCRATCH, f"rl-{tag}-{uuid4().hex[:6]}.sqlite")


def make_engine(engine_name: str, path: str | None) -> AsyncEngine:
    if engine_name == "sqlite":
        engine = create_async_engine(f"sqlite+aiosqlite:///{path}")

        def on_connect(dbapi, _):
            for p in SQLITE_PRAGMAS:
                dbapi.execute(p)

        event.listen(engine.sync_engine, "connect", on_connect)
        return engine
    engine = create_async_engine(PG_URL)
    if PG_JIT_OFF:

        def jit_off(dbapi, _):
            cursor = dbapi.cursor()
            cursor.execute("SET jit = off")
            cursor.close()

        event.listen(engine.sync_engine, "connect", jit_off)
    return engine


async def load(
    engine_name: str,
    path: str | None,
    t: Names,
    w: World,
    domains: Domains,
    lab: list[tuple[int, int]],
    chunks: list[tuple[int, int, int]],
) -> dict[str, float]:
    """Create the tables and bulk-load them through the raw driver; return the load timings."""
    d = "postgresql" if engine_name == "postgres" else "sqlite"
    entries = [(rid, p, o, pub, dom) for (rid, p, o), (pub, dom) in zip(w.rows, lab)]
    grants = [(p, prefix, lvl) for p, prefix, lvl in w.grants] + [("*", p, lvl) for p, lvl in w.star.items()]
    members = [(u, g) for u, gs in w.members.items() for g in gs]
    timings: dict[str, float] = {}
    t0 = time.perf_counter()
    if d == "sqlite":
        assert path is not None
        con = sqlite3.connect(path)
        con.execute("PRAGMA page_size = 16384")
        con.execute("PRAGMA journal_mode = OFF")
        con.execute("PRAGMA synchronous = OFF")
        for s in ddl(d, t):
            con.execute(s)
        con.executemany(f"INSERT INTO {t.e} VALUES (?,?,?,?,?)", entries)
        con.executemany(f"INSERT INTO {t.c} VALUES (?,?,?)", chunks)
        con.executemany(f"INSERT INTO {t.d} VALUES (?,?,?)", domains.rows())
        con.executemany(f"INSERT INTO {t.g} VALUES (?,?,?)", grants)
        con.executemany(f"INSERT INTO {t.m} VALUES (?,?)", members)
        con.commit()
        con.close()
    else:
        import asyncpg

        con = await asyncpg.connect(PG_URL.replace("+asyncpg", ""))
        for s in ddl(d, t):
            await con.execute(s)
        await con.copy_records_to_table(
            t.e, records=entries, columns=["id", "path", "owner_id", "public_level", "domain_id"]
        )
        await con.copy_records_to_table(t.c, records=chunks, columns=["id", "entry_id", "score"])
        await con.copy_records_to_table(t.d, records=domains.rows(), columns=["id", "path", "public_level"])
        await con.copy_records_to_table(t.g, records=grants, columns=["principal_id", "path_prefix", "level"])
        await con.copy_records_to_table(t.m, records=members, columns=["principal_id", "group_id"])
        await con.close()
    timings["rows"] = time.perf_counter() - t0
    return timings


async def build_indexes(engine: AsyncEngine, engine_name: str, t: Names) -> list[tuple[str, float, int]]:
    """Build each index in turn; return ``(name, seconds, bytes)``."""
    out: list[tuple[str, float, int]] = []
    async with engine.begin() as conn:
        if engine_name == "sqlite":
            await conn.execute(text("PRAGMA journal_mode = WAL"))
        for name, stmt in index_ddl(t).items():
            t0 = time.perf_counter()
            await conn.execute(text(stmt))
            secs = time.perf_counter() - t0
            out.append((name, secs, await index_bytes(conn, engine_name, name)))
        for name in (t.e, t.c, t.d, t.g, t.m):
            await conn.execute(text(f"ANALYZE {name}"))
    return out


async def index_bytes(conn, engine_name: str, name: str) -> int:
    if engine_name == "sqlite":
        return int(
            (
                await conn.execute(text("SELECT coalesce(sum(pgsize), 0) FROM dbstat WHERE name = :n"), {"n": name})
            ).scalar()
        )
    return int((await conn.execute(text("SELECT pg_relation_size(CAST(:n AS regclass))"), {"n": name})).scalar())


async def drop_all(engine: AsyncEngine, t: Names) -> None:
    async with engine.begin() as conn:
        for name in (t.e, t.c, t.d, t.g, t.m):
            await conn.execute(text(f"DROP TABLE IF EXISTS {name}"))


# ---------------------------------------------------------------------------
# Timing and recall
# ---------------------------------------------------------------------------


async def timed(
    engine: AsyncEngine, sql: str, params: dict[str, Any], reps: int, *, cap_s: float = 20.0
) -> tuple[float, float, Any]:
    """Cold ms (fresh connection, first run), warm median ms, and the first answer."""
    await engine.dispose()
    async with engine.connect() as conn:
        t0 = time.perf_counter()
        answer = (await conn.execute(text(sql), params)).all()
        cold = (time.perf_counter() - t0) * 1000
        await conn.rollback()
        if cold / 1000 > cap_s:
            return cold, float("nan"), answer
        warm: list[float] = []
        for _ in range(reps):
            t0 = time.perf_counter()
            (await conn.execute(text(sql), params)).all()
            warm.append((time.perf_counter() - t0) * 1000)
            await conn.rollback()
    return cold, statistics.median(warm), answer


def recall(statement: str, answer: Any, exact: Any) -> str:
    if statement == "count":
        got = answer[0][0]
        return "exact" if got == exact else f"{got} != {exact}"
    got = {r[0] for r in answer}
    hit = len(got & exact) / len(exact) if exact else 1.0
    extra = len(got - exact)
    return ("exact" if hit == 1.0 and not extra else f"{hit:.4f}") + (f" (+{extra} extra)" if extra else "")


async def plan(engine: AsyncEngine, engine_name: str, sql: str, params: dict[str, Any]) -> str:
    async with engine.connect() as conn:
        if engine_name == "sqlite":
            rows = (await conn.execute(text("EXPLAIN QUERY PLAN " + sql), params)).all()
            return "\n".join(("  " * 0) + str(r[-1]) for r in rows)
        rows = (await conn.execute(text("EXPLAIN (ANALYZE, BUFFERS) " + sql), params)).all()
        return "\n".join(r[0] for r in rows)


def ms(v: float) -> str:
    return "n/a" if v != v else (f"{v:,.1f}" if v < 100 else f"{v:,.0f}")


def mb(b: int) -> str:
    return f"{b / 1e6:,.1f} MB"


# ---------------------------------------------------------------------------
# The shipped resolver, on a sample
# ---------------------------------------------------------------------------


def shipped_check(w: World, spec: dict, exact: set[int], sample: int, rng: random.Random) -> str:
    """Resolve the same world with vfs's shipped resolver and compare ``admits`` on a sample."""
    if spec.get("system"):
        return "skipped (system)"
    rows = [GrantRow("*", p, LEVEL_NAME[lvl]) for p, lvl in w.star.items()]
    rows += [GrantRow(p, prefix, LEVEL_NAME[lvl]) for p, prefix, lvl in w.grants]
    if spec.get("anonymous"):
        closures = {"anon": frozenset()}
    else:
        closures = {m: frozenset(w.members[m]) for m in spec["subjects"]}
    t0 = time.perf_counter()
    rights = resolve(closures, rows, "read", owner_floor=not spec.get("anonymous"))
    resolve_s = time.perf_counter() - t0
    picked = rng.sample(w.rows, min(sample, len(w.rows)))
    t0 = time.perf_counter()
    disagree = sum(1 for rid, p, o in picked if rights.admits(p, o) != (rid in exact))
    admits_s = time.perf_counter() - t0
    arms = len(rights.arms)
    holes = sum(len(a.holes) for a in rights.arms)
    return (
        f"{len(picked):,} rows, {disagree} disagreements; shipped resolve {resolve_s * 1000:,.0f} ms "
        f"({arms} arms, {holes:,} holes), admits {admits_s / len(picked) * 1e6:,.0f} us/row"
    )


# ---------------------------------------------------------------------------
# The read run
# ---------------------------------------------------------------------------


async def read_run(engine_name: str, n: int, reps: int, chunks_per_file: int, sample: int) -> None:
    started = time.perf_counter()
    lines: list[str] = []

    def say(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    w = build(n)
    domains = Domains(w)
    lab = labels(w, domains)
    rng = random.Random(7)
    files = [rid for rid, p, _ in w.rows if p.endswith(".md")]
    scores = rng.sample(range(len(files) * chunks_per_file * 4), len(files) * chunks_per_file)
    chunks = [(i, fid, scores[i]) for i, fid in enumerate(f for f in files for _ in range(chunks_per_file))]
    score_of = {i: s for i, _, s in chunks}
    say(
        f"## {engine_name}{' (jit off)' if PG_JIT_OFF else ''} — N={n:,} users: {len(w.rows):,} entries, {len(chunks):,} chunks "
        f"({chunks_per_file}/file), {len(w.grants):,} grant rows, {len(w.star):,} posture rows, "
        f"{len(domains.id_of):,} domains"
    )
    say()

    path = sqlite_path(f"n{n}") if engine_name == "sqlite" else None
    t = names(f"rl_{uuid4().hex[:8]}_")
    engine = make_engine(engine_name, path)
    try:
        timings = await load(engine_name, path, t, w, domains, lab, chunks)
        say(f"Load: rows in {timings['rows']:.1f}s.")
        say()
        say("### Indexes")
        say()
        say("| index | build s | size |")
        say("|---|---|---|")
        for name, secs, size in await build_indexes(engine, engine_name, t):
            say(f"| {name[len(t.e) - 1 :]} | {secs:.1f} | {mb(size)} |")
        async with engine.connect() as conn:
            e_bytes = await index_bytes(conn, engine_name, t.e)
        say(f"| (entries table itself) | | {mb(e_bytes)} |")
        say()

        # Truth per caller, cached per N so the second engine's run reuses it.
        specs = callers(w)
        cache = os.path.join(SCRATCH, f"truth-{n}.pkl")
        exact: dict[str, set[int]] = {}
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                exact = pickle.load(f)
        else:
            t0 = time.perf_counter()
            for label, spec in specs.items():
                exact[label] = truth(
                    w, spec["subjects"], READ, anonymous=spec.get("anonymous", False), system=spec.get("system", False)
                )
            with open(cache + ".tmp", "wb") as f:
                pickle.dump(exact, f)
            os.replace(cache + ".tmp", cache)
            say(f"Truth computed in Python in {time.perf_counter() - t0:.1f}s.")
        scope = ("/shared/s0001/", "/shared/s00010")
        in_scope = {rid for rid, p, _ in w.rows if scope[0] < p < scope[1]}

        say("### Callers")
        say()
        say("| caller | subjects | grants held | visible entries | shipped `Rights.admits` on a sample |")
        say("|---|---|---|---|---|")
        for label, spec in specs.items():
            held = sum(len(w.by_principal.get(p, ())) for m in spec["subjects"] for p in w.principals_of(m))
            check = shipped_check(w, spec, exact[label], sample, random.Random(11))
            say(f"| {label} | {', '.join(spec['subjects']) or '—'} | {held} | {len(exact[label]):,} | {check} |")
        say()

        # 1. Compile: pure Python from the caller's own grants, then the SQL fetch that feeds it.
        say("### Compile per caller (the caller's own grants → sorted pieces)")
        say()
        say(
            "| caller | level | points | opens | owner pieces | bind bytes | compile us (median of 200) | grants fetch cold ms | warm ms |"
        )
        say("|---|---|---|---|---|---|---|---|---|")
        compiled: dict[str, dict[int, Any]] = {}
        for label, spec in specs.items():
            compiled[label] = {}
            if spec.get("anonymous") or spec.get("system"):
                continue
            for level in (READ, READ_WRITE):
                samples = []
                for _ in range(200):
                    c = compile_rights(w, spec["subjects"], level)
                    samples.append(c.compile_us)
                compiled[label][level] = c
                owner_pieces = sum(len(p.points) + len(p.opens) for _, p in c.owners if p is not None)
                fetch = await timed(
                    engine,
                    grants_fetch_sql(engine_name, t),
                    {"subs": grants_fetch_binds(engine_name, w, spec["subjects"])},
                    reps,
                )
                say(
                    f"| {label} | {LEVEL_NAME[level]} | {len(c.arms.points)} | {len(c.arms.opens)} | {owner_pieces} | "
                    f"{c.bind_bytes:,} | {statistics.median(samples):,.0f} | {ms(fetch[0])} | {ms(fetch[1])} |"
                )
        say()

        # Domain lists via SQL: the domain variant's compile.
        d = Dialect("postgresql" if engine_name == "postgres" else "sqlite")
        say("### Domain lists (the `domain_id` variant's compile, one SQL statement)")
        say()
        say("| caller | domains in list | bind bytes | cold ms | warm ms |")
        say("|---|---|---|---|---|")
        caller_objs: dict[str, Caller] = {}
        for label, spec in specs.items():
            if spec.get("system"):
                caller_objs[label] = Caller(None, False, True)
                continue
            c = compiled[label].get(READ)
            sql, params = domain_list_sql(d, t, c.arms if c else None, READ)
            cold, warm, answer = await timed(engine, sql, params, reps)
            ids = sorted(r[0] for r in answer)
            owner_domains: dict[str, list[int]] | None = None
            if c is not None and len(c.owners) > 1:
                owner_domains = {}
                async with engine.connect() as conn:
                    for owner, pieces in c.owners:
                        sql2, params2 = domain_list_sql(d, t, pieces, READ)
                        owner_domains[owner] = sorted(r[0] for r in (await conn.execute(text(sql2), params2)).all())
            caller_objs[label] = Caller(c, bool(spec.get("anonymous")), False, ids, owner_domains)
            say(f"| {label} | {len(ids):,} | {len(json.dumps(ids).encode()):,} | {ms(cold)} | {ms(warm)} |")
        say()

        # 2. Statements per caller and variant, with recall.
        say(f"### Statements — cold = fresh connection, warm = median of {reps} (ms); recall against the Python truth")
        say()
        say("| caller | statement | " + " | ".join(f"{v}: cold / warm / recall" for v in VARIANTS) + " |")
        say("|---|---|" + "---|" * len(VARIANTS))
        plans: list[tuple[str, str, str]] = []
        for label, spec in specs.items():
            caller = caller_objs[label]
            vis = exact[label]
            visible_chunks = [i for i, eid, _ in chunks if eid in vis]
            top = set(sorted(visible_chunks, key=score_of.__getitem__)[:10])
            truths = {
                "entries": vis,
                "scoped": vis & in_scope,
                "count": len(visible_chunks),
                "top10": top,
                "top10 probe": top,
            }
            for statement in STATEMENTS:
                cells = []
                for variant in VARIANTS:
                    if caller.system and variant == "domain":
                        cells.append("—")
                        continue
                    sql, params = statements(d, t, variant, caller, READ, scope)[statement]
                    cold, warm, answer = await timed(engine, sql, params, reps)
                    cells.append(f"{ms(cold)} / {ms(warm)} / {recall(statement, answer, truths[statement])}")
                    if label == "ordinary" and statement in ("entries", "count", "top10", "top10 probe"):
                        plans.append((variant, statement, await plan(engine, engine_name, sql, params)))
                say(f"| {label} | {statement} | " + " | ".join(cells) + " |")
        say()

        # 5. Invalidation: who one write invalidates, and what the recompute costs.
        say("### Cache invalidation at this N")
        say()
        heavy_members = len(w.group_members[HEAVY_GROUP])
        typical = statistics.median(len(v) for v in w.group_members.values())
        c = compiled["ordinary"][READ]
        fetch = await timed(
            engine,
            grants_fetch_sql(engine_name, t),
            {"subs": grants_fetch_binds(engine_name, w, specs["ordinary"]["subjects"])},
            reps,
        )
        per_caller_ms = fetch[1] + c.compile_us / 1000
        say(
            "One cached caller recomputes by fetching its grant rows and merging them: "
            f"about {per_caller_ms:.2f} ms warm here (fetch {ms(fetch[1])} ms + compile {c.compile_us:,.0f} us)."
        )
        say()
        say(
            "| write | global revision invalidates | per-principal / per-group / posture revisions invalidate | recompute at global (ms) | at granular (ms) |"
        )
        say("|---|---|---|---|---|")
        for write, granular in (
            ("grant to one user", 1),
            ("grant to a typical group", int(typical)),
            ("grant to the heavy group", heavy_members),
            ("posture change (any subtree)", 0),
        ):
            say(f"| {write} | {n:,} | {granular:,} | {n * per_caller_ms:,.0f} | {granular * per_caller_ms:,.0f} |")
        say()
        say(
            "Under the row-label shape a posture change invalidates no compiled rights: the posture is on the rows, "
            "not in the caller's pieces. The relabel UPDATE is its cost (see the writes run)."
        )
        say()

        say("### Plans (ordinary caller)")
        say()
        for variant, statement, p in plans:
            say(f"**{variant} / {statement}**")
            say()
            say("```")
            say(p)
            say("```")
            say()
    finally:
        await drop_all(engine, t)
        await engine.dispose()
        if path and os.path.exists(path):
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(path + suffix):
                    os.remove(path + suffix)
    say(f"Total wall time {time.perf_counter() - started:.0f}s.")
    write_lines(f"{engine_name}-{n}{RUN_SUFFIX}.md", lines)


def grants_fetch_sql(engine_name: str, t: Names) -> str:
    """The rows that feed the compile: every grant naming the subject or one of its groups."""
    if engine_name == "postgres":
        return (
            f"SELECT g.principal_id, g.path_prefix, g.level FROM {t.g} g WHERE g.principal_id = ANY(CAST(:subs AS text[])) "
            f"OR g.principal_id IN (SELECT m.group_id FROM {t.m} m WHERE m.principal_id = ANY(CAST(:subs AS text[])))"
        )
    return (
        f"SELECT g.principal_id, g.path_prefix, g.level FROM {t.g} g WHERE g.principal_id IN (SELECT value FROM json_each(:subs)) "
        f"OR g.principal_id IN (SELECT m.group_id FROM {t.m} m WHERE m.principal_id IN (SELECT value FROM json_each(:subs)))"
    )


def grants_fetch_binds(engine_name: str, w: World, subjects: list[str]) -> Any:
    return list(subjects) if engine_name == "postgres" else json.dumps(list(subjects))


def write_lines(filename: str, lines: list[str]) -> None:
    os.makedirs(os.path.join(HERE, "runs"), exist_ok=True)
    out = os.path.join(HERE, "runs", filename)
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"→ {out}", flush=True)


# ---------------------------------------------------------------------------
# The writes run: relabel on posture change, a new grant boundary, and a move
# ---------------------------------------------------------------------------


async def writes_run(engine_name: str, reps: int, big: int) -> None:
    started = time.perf_counter()
    lines: list[str] = []

    def say(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    w = build(1_000)
    extra = {"/mid": 1_000, "/mv": 10_000, "/big": big}
    for folder, count in extra.items():
        w.add_row(folder)
        for i in range(count):
            w.add_row(f"{folder}/f{i:07d}.md", "u000000")
    domains = Domains(w)
    lab = labels(w, domains)
    say(
        f"## {engine_name} — writes: 1,000-user world plus /mid ({extra['/mid']:,} rows), /mv ({extra['/mv']:,}), "
        f"/big ({big:,}); {len(w.rows):,} entries"
    )
    say()
    path = sqlite_path("writes") if engine_name == "sqlite" else None
    t = names(f"rl_{uuid4().hex[:8]}_")
    engine = make_engine(engine_name, path)
    d = "postgresql" if engine_name == "postgres" else "sqlite"
    star = dict(w.star)
    try:
        await load(engine_name, path, t, w, domains, lab, [])
        await build_indexes(engine, engine_name, t)
        say("| operation | statement shape | statements | rows touched | total ms (median of runs) | labels after |")
        say("|---|---|---|---|---|---|")

        async def check(label: str) -> str:
            """Compare every row's stored public_level with the Python labeller under the current postures."""
            expect = {rid: public_level(star, p) for rid, p, _ in w.rows}
            async with engine.connect() as conn:
                rows = (await conn.execute(text(f"SELECT id, public_level FROM {t.e}"))).all()
            wrong = sum(1 for rid, pub in rows if expect[rid] != pub)
            return "all correct" if wrong == 0 else f"{wrong:,} wrong"

        dl = Dialect(d)

        async def relabel(conn, level: int, pieces: Pieces, chunk_rows: int | None) -> tuple[int, int]:
            """Relabel the rows *pieces* name; returns (statements, rows touched).

            Whole mode: the range join, at most 500 pieces per statement
            (bounded binds, unbounded rows). Chunked mode: points as
            above, each open range walked by keyset in *chunk_rows*
            steps (bounded rows, two statements per range at least).
            """
            stmts = touched = 0
            for i in range(0, len(pieces.points), 500):
                frag, value, binds = dl.points("p", pieces.points[i : i + 500])
                res = await conn.execute(
                    text(
                        f"UPDATE {t.e} SET public_level = :lvl WHERE id IN "
                        f"(SELECT e.id FROM {frag} JOIN {t.e} e ON e.path = {value})"
                    ),
                    {"lvl": level, **binds},
                )
                stmts += 1
                touched += res.rowcount
            if chunk_rows is None:
                for i in range(0, len(pieces.opens), 500):
                    frag, lo, hi, binds = dl.opens("r", pieces.opens[i : i + 500])
                    res = await conn.execute(
                        text(
                            f"UPDATE {t.e} SET public_level = :lvl WHERE id IN "
                            f"(SELECT e.id FROM {frag} JOIN {t.e} e ON e.path > {lo} AND e.path < {hi})"
                        ),
                        {"lvl": level, **binds},
                    )
                    stmts += 1
                    touched += res.rowcount
                return stmts, touched
            for lo, hi in pieces.opens:
                cur = lo
                while True:
                    bound = (
                        await conn.execute(
                            text(
                                f"SELECT path FROM {t.e} WHERE path > :cur AND path < :hi ORDER BY path LIMIT 1 OFFSET :k"
                            ),
                            {"cur": cur, "hi": hi, "k": chunk_rows - 1},
                        )
                    ).scalar()
                    stmts += 1
                    if bound is None:
                        res = await conn.execute(
                            text(f"UPDATE {t.e} SET public_level = :lvl WHERE path > :cur AND path < :hi"),
                            {"lvl": level, "cur": cur, "hi": hi},
                        )
                        stmts += 1
                        touched += res.rowcount
                        break
                    res = await conn.execute(
                        text(f"UPDATE {t.e} SET public_level = :lvl WHERE path > :cur AND path <= :b"),
                        {"lvl": level, "cur": cur, "b": bound},
                    )
                    stmts += 1
                    touched += res.rowcount
                    cur = bound
            return stmts, touched

        async def run_posture(prefix: str, new_level: int, chunk_rows: int | None, label: str) -> None:
            """Set the posture at *prefix* and relabel its domain: its cover minus every deeper posture."""
            deeper = [p for p in star if p != prefix and p.startswith(prefix.rstrip("/") + "/")]
            pieces = split(relabel_spans(prefix, deeper))
            samples: list[float] = []
            stmts = touched = 0
            for r in range(reps):
                level = new_level if r % 2 == 0 else (NONE if new_level != NONE else READ)
                star[prefix] = level
                t0 = time.perf_counter()
                async with engine.begin() as conn:
                    stmts, touched = await relabel(conn, level, pieces, chunk_rows)
                samples.append((time.perf_counter() - t0) * 1000)
            shape = (
                f"{len(pieces.points)} points + {len(pieces.opens)} open ranges ({len(deeper):,} deeper postures cut); "
                + (
                    "range join, <=500 pieces/statement"
                    if chunk_rows is None
                    else f"keyset chunks of {chunk_rows:,} rows"
                )
            )
            say(
                f"| {label} | {shape} | {stmts:,} | {touched:,} | {statistics.median(samples):,.0f} | {await check(label)} |"
            )

        async def run_domain_update(domain_path: str, new_level: int, label: str) -> None:
            """The domain variant: relabel by ``domain_id`` (one bind, however many rows)."""
            did = domains.id_of.get(domain_path)
            samples: list[float] = []
            touched = 0
            old = star.get(domain_path, READ_WRITE)
            for r in range(reps):
                level = new_level if r % 2 == 0 else old
                star[domain_path] = level
                t0 = time.perf_counter()
                async with engine.begin() as conn:
                    res = await conn.execute(
                        text(f"UPDATE {t.e} SET public_level = :lvl WHERE domain_id = :d"), {"lvl": level, "d": did}
                    )
                    touched = res.rowcount
                samples.append((time.perf_counter() - t0) * 1000)
            say(
                f"| {label} | `domain_id = :d` | 1 | {touched:,} | {statistics.median(samples):,.0f} | {await check(label)} |"
            )

        # A posture at a new prefix also makes a new domain; the domain-id relabel is the same UPDATE
        # over the same spans with a second SET column, so it is not timed separately.
        await run_posture("/mid", READ, None, "posture /mid → shared (1,000 rows)")
        await run_posture("/mid", READ, 500, "posture /mid → shared, chunked")
        await run_posture("/big", READ, None, f"posture /big → shared ({big:,} rows)")
        await run_posture("/big", READ, 50_000, f"posture /big → shared, chunked")
        await run_posture("/big", READ, 200_000, f"posture /big → shared, chunked")
        await run_posture("/", READ, None, "posture / → shared (root minus every deeper posture)")
        await run_posture("/", READ, 50_000, "posture / → shared, chunked")

        # The domain variant's relabel for the same changes. /mid and /big are their own domains
        # once a posture exists there; register them so domain_id matches.
        async with engine.begin() as conn:
            for p in ("/mid", "/big"):
                did = max(domains.id_of.values()) + 1
                domains.id_of[p] = did
                await conn.execute(text(f"INSERT INTO {t.d} VALUES (:i, :p, :l)"), {"i": did, "p": p, "l": star[p]})
                await conn.execute(
                    text(f"UPDATE {t.e} SET domain_id = :i WHERE path = :p OR (path >= :lo AND path < :hi)"),
                    {"i": did, "p": p, "lo": p + "/", "hi": p + "0"},
                )
        await run_domain_update("/mid", READ_WRITE, "domain variant: posture /mid (1,000 rows)")
        await run_domain_update("/big", READ_WRITE, f"domain variant: posture /big ({big:,} rows)")

        # A new grant boundary: public_level variant writes no row; domain variant relabels the subtree.
        samples = []
        for r in range(reps):
            new_id = max(domains.id_of.values()) + 1 + r
            t0 = time.perf_counter()
            async with engine.begin() as conn:
                await conn.execute(
                    text(f"INSERT INTO {t.d} VALUES (:i, :p, :l)"), {"i": new_id, "p": "/big/sub", "l": star["/big"]}
                )
                res = await conn.execute(
                    text(f"UPDATE {t.e} SET domain_id = :i WHERE path >= :lo AND path < :hi"),
                    {"i": new_id, "lo": "/big/", "hi": "/big0"},
                )
                await conn.execute(text(f"DELETE FROM {t.d} WHERE id = :i"), {"i": new_id})
            samples.append((time.perf_counter() - t0) * 1000)
        say(f"| grant at a new prefix over /big: public_level variant | no row write | 0 | 0 | 0 | n/a |")
        say(
            f"| grant at a new prefix over /big: domain variant | `path` range | 1 | {res.rowcount:,} | {statistics.median(samples):,.0f} | n/a |"
        )

        # Move /mv (open, under the root) into /home/u000000 (private): every row takes the destination's label.
        src, dst = "/mv", "/home/u000000/mv"
        dst_level = public_level(star, dst)
        dst_domain = domains.id_of["/home/u000000"]
        samples = []
        for r in range(reps):
            a, b = (src, dst) if r % 2 == 0 else (dst, src)
            lvl = dst_level if r % 2 == 0 else public_level(star, src)
            dom = dst_domain if r % 2 == 0 else domains.id_of["/"]
            cut = len(a) + 1
            t0 = time.perf_counter()
            async with engine.begin() as conn:
                sql = (
                    f"UPDATE {t.e} SET path = :b || substr(path, :cut), public_level = :lvl, domain_id = :dom "
                    f"WHERE path = :a OR (path >= :lo AND path < :hi)"
                )
                res = await conn.execute(
                    text(sql), {"a": a, "b": b, "cut": cut, "lvl": lvl, "dom": dom, "lo": a + "/", "hi": a + "0"}
                )
            samples.append((time.perf_counter() - t0) * 1000)
        if reps % 2 == 0:  # leave the subtree at the destination for the check
            async with engine.begin() as conn:
                await conn.execute(
                    text(sql),
                    {
                        "a": src,
                        "b": dst,
                        "cut": len(src) + 1,
                        "lvl": dst_level,
                        "dom": dst_domain,
                        "lo": src + "/",
                        "hi": src + "0",
                    },
                )
        async with engine.connect() as conn:
            moved = (
                await conn.execute(
                    text(
                        f"SELECT count(*), min(public_level), max(public_level), min(domain_id), max(domain_id) "
                        f"FROM {t.e} WHERE path = :p OR (path >= :lo AND path < :hi)"
                    ),
                    {"p": dst, "lo": dst + "/", "hi": dst + "0"},
                )
            ).one()
            left = (
                await conn.execute(
                    text(f"SELECT count(*) FROM {t.e} WHERE path = :p OR (path >= :lo AND path < :hi)"),
                    {"p": src, "lo": src + "/", "hi": src + "0"},
                )
            ).scalar()
        ok = (
            moved[0] == extra["/mv"] + 1
            and moved[1] == moved[2] == dst_level
            and moved[3] == moved[4] == dst_domain
            and left == 0
        )
        say(
            f"| move /mv → /home/u000000/mv (10,001 rows, open → private) | one `path` range UPDATE | 1 | {res.rowcount:,} | "
            f"{statistics.median(samples):,.0f} | {'all take the destination label' if ok else 'WRONG: ' + str(moved)} |"
        )

        # The per-write label lookup: the nearest boundary of a new path, through the domain table.
        new_path = "/shared/s0003/sub/deeper/file.md"
        chain = ancestors_and_self(new_path)
        if d == "postgresql":
            sql = f"SELECT id, public_level FROM {t.d} WHERE path = ANY(CAST(:c AS text[])) ORDER BY length(path) DESC LIMIT 1"
            binds: Any = {"c": chain}
        else:
            sql = f"SELECT id, public_level FROM {t.d} WHERE path IN (SELECT value FROM json_each(:c)) ORDER BY length(path) DESC LIMIT 1"
            binds = {"c": json.dumps(chain)}
        cold, warm, answer = await timed(engine, sql, binds, reps)
        say(
            f"| label lookup for one new row (nearest boundary of a {len(chain)}-deep path) | `path IN (ancestors)` on the domain table | 1 | 1 | "
            f"{warm:.2f} (cold {cold:.1f}) | {answer[0]} |"
        )
        say()
    finally:
        await drop_all(engine, t)
        await engine.dispose()
        if path and os.path.exists(path):
            for suffix in ("", "-wal", "-shm"):
                if os.path.exists(path + suffix):
                    os.remove(path + suffix)
    say(f"Total wall time {time.perf_counter() - started:.0f}s.")
    write_lines(f"{engine_name}-writes.md", lines)


# ---------------------------------------------------------------------------
# The semantics run: the traps the brief names, executed on SQLite
# ---------------------------------------------------------------------------


async def semantics_run() -> None:
    """Private home + own grant, nested shared inside private, sibling trap, move across a boundary.

    A 1,000-user world; then a ``shared`` posture is set on
    ``/home/u000001/pub`` (five rows) and ``/mv`` (open, under the root)
    is moved into ``/home/u000002``. Every caller's visible set is read
    through both variants and compared with the truth function run on
    the changed world; the named rows are listed by hand.
    """
    lines: list[str] = []

    def say(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    w = build(1_000)
    pub = "/home/u000001/pub"
    w.add_row(pub)
    for i in range(5):
        w.add_row(f"{pub}/p{i}.md", "u000001")
    w.add_row("/mv")
    for i in range(10):
        w.add_row(f"/mv/m{i}.md", "u000005")
    domains = Domains(w)
    lab = labels(w, domains)
    path = sqlite_path("sem")
    t = names(f"rl_{uuid4().hex[:8]}_")
    engine = make_engine("sqlite", path)
    d = Dialect("sqlite")
    try:
        await load("sqlite", path, t, w, domains, lab, [])
        await build_indexes(engine, "sqlite", t)
        # 1. nested shared inside the private home: a new posture row, a new domain, relabel its cover.
        w.star[pub] = READ
        did = max(domains.id_of.values()) + 1
        domains.id_of[pub] = did
        async with engine.begin() as conn:
            await conn.execute(text(f"INSERT INTO {t.d} VALUES (:i, :p, :l)"), {"i": did, "p": pub, "l": READ})
            await conn.execute(
                text(
                    f"UPDATE {t.e} SET public_level = :l, domain_id = :i WHERE path = :p OR (path >= :lo AND path < :hi)"
                ),
                {"l": READ, "i": did, "p": pub, "lo": pub + "/", "hi": pub + "0"},
            )
        # 2. move /mv into u000002's private home: path rewrite plus the destination's labels.
        dst = "/home/u000002/mv"
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    f"UPDATE {t.e} SET path = :b || substr(path, :cut), public_level = :l, domain_id = :i "
                    f"WHERE path = :a OR (path >= :lo AND path < :hi)"
                ),
                {
                    "a": "/mv",
                    "b": dst,
                    "cut": len("/mv") + 1,
                    "l": NONE,
                    "i": domains.id_of["/home/u000002"],
                    "lo": "/mv/",
                    "hi": "/mv0",
                },
            )
        w.rows = [(rid, dst + p[len("/mv") :] if p == "/mv" or p.startswith("/mv/") else p, o) for rid, p, o in w.rows]
        by_id = {rid: p for rid, p, _ in w.rows}
        cases = {
            "anonymous": {"subjects": [], "anonymous": True},
            "u000001 (owns the home with the nested shared folder)": {"subjects": ["u000001"]},
            "u000002 (owns the home the subtree moved into)": {"subjects": ["u000002"]},
            "u000005 (owned the moved rows; no grant on the destination)": {"subjects": ["u000005"]},
            "u000003 (a bystander)": {"subjects": ["u000003"]},
        }
        named = [
            pub,
            f"{pub}/p0.md",
            "/home/u000001",
            "/home/u000001/f000.md",
            "/home/u000001-x",
            f"{dst}/m0.md",
            "/home/u000002/f000.md",
        ]
        say(
            "## Semantics on SQLite — a 1,000-user world, then `shared` at `/home/u000001/pub` and `/mv` moved into `/home/u000002`"
        )
        say()
        say("| caller | variant | visible | matches truth | " + " | ".join(f"`{p}`" for p in named) + " |")
        say("|---|---|---|---|" + "---|" * len(named))
        for label, spec in cases.items():
            exact = truth(w, spec["subjects"], READ, anonymous=spec.get("anonymous", False))
            c = compile_rights(w, spec["subjects"], READ) if spec["subjects"] else None
            sql, params = domain_list_sql(d, t, c.arms if c else None, READ)
            async with engine.connect() as conn:
                ids = sorted(r[0] for r in (await conn.execute(text(sql), params)).all())
            caller = Caller(c, bool(spec.get("anonymous")), False, ids, None)
            for variant in VARIANTS:
                sql, params = visible_sql(d, t, variant, caller, READ)
                async with engine.connect() as conn:
                    got = {r[0] for r in (await conn.execute(text(sql), params)).all()}
                seen = {by_id[i] for i in got}
                cells = " | ".join("yes" if p in seen else "no" for p in named)
                say(f"| {label} | {variant} | {len(got):,} | {'exact' if got == exact else 'MISMATCH'} | {cells} |")
        say()
        say(
            "Reading the columns: the nested shared folder is visible to everyone while the rest of the home stays hidden; "
            "the owner sees all of it through the grant; the sibling trap `/home/u000001-x` is visible to nobody; the moved rows "
            "are visible to the destination's owner through the grant and hidden from everyone else — except their former "
            "owner, who still sees them through the owner floor (`owner_id = me` is mount-wide in the spec's rules and in the "
            "shipped single-subject owner arm). The truth function and both variants agree on that; whether a move into "
            "another user's private home should keep the mover's floor is a question for the spec."
        )
    finally:
        await drop_all(engine, t)
        await engine.dispose()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.remove(path + suffix)
    write_lines("sqlite-semantics.md", lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["sqlite", "postgres"])
    ap.add_argument("--n", type=int, default=1_000)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--chunks", type=int, default=3, help="chunks per file")
    ap.add_argument("--sample", type=int, default=5_000, help="rows checked against the shipped resolver")
    ap.add_argument("--writes", action="store_true")
    ap.add_argument("--semantics", action="store_true")
    ap.add_argument("--big", type=int, default=1_000_000)
    a = ap.parse_args()
    if a.semantics:
        asyncio.run(semantics_run())
    elif a.writes:
        asyncio.run(writes_run(a.engine, a.reps, a.big))
    else:
        asyncio.run(read_run(a.engine, a.n, a.reps, a.chunks, a.sample))
