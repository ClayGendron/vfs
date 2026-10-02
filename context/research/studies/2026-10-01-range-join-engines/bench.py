"""ADR 072's range join, prototyped on all five engines, with a recall check.

ADR 072 says a caller's rights should reach SQL as one bound list of
sorted path ranges, unpacked by the engine and joined to the ``path``
index, with entries filtered before any chunk-side table is touched.
This script measures that shape against the two others on every engine:

- ``arms``: today's shipped predicate (``visibility_clauses``), one
  ``path = :p OR path LIKE :p/%`` arm per prefix, fanned into clauses,
  tested against chunk rows joined to entries.
- ``literal``: ADR 072 rule 5, the same pieces inline as byte ranges
  (``path >= :lo AND path < :hi``). Only timed for small rights.
- ``join``: ADR 072 rules 2 to 4, one JSON or array bind unpacked by
  ``json_each`` / ``unnest`` / ``OPENJSON`` / ``JSON_TABLE``, joined to
  the path index, owner arms as a ``UNION`` branch, chunks filtered by
  ``entry_id IN (visible entries)``.

Three statements per shape, the ones the glean profile blamed:
the visible entries, the visible chunk count (``_visible_corpus``'s
job), and the top 10 visible chunks by a score column (the vector
leg's shape, with an integer score standing in for distance).

Every shape's answer is checked against ``Rights.admits`` run in Python
over every row. The recall column is the share of the exact answer a
shape returned; ``extra`` counts rows it returned that it must not.

    uv run --no-sync python bench.py --engine sqlite
    VFS_TEST_POSTGRES_URL=... uv run --no-sync python bench.py --engine postgres

Study code only: nothing here is imported by vfs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import time
from typing import Any, NamedTuple
from uuid import uuid4

from sqlalchemy import (
    CLOB,
    BigInteger,
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    and_,
    bindparam,
    event,
    func,
    insert,
    or_,
    select,
    text,
)
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from vfs.models.rows import MSSQL_UTF8_COLLATION, BytewiseString
from vfs.storage.backends.database.dialects import profile_for
from vfs.storage.backends.database.rights import visibility_clauses
from vfs.storage.grants import ROOT, GrantRow, Rights, resolve

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ENV = {
    "postgres": "VFS_TEST_POSTGRES_URL",
    "mssql": "VFS_TEST_MSSQL_URL",
    "oracle": "VFS_TEST_ORACLE_URL",
    "mariadb": "VFS_TEST_MARIADB_URL",
}
CHUNKS_PER_FILE = 3
LITERAL_MAX_PIECES = 64
SLOW_CAP_S = 1.0
SHAPES = ("arms", "literal", "join IN", "join derived")
NEXT = "\x01"  # the least byte a lawful path can follow a prefix with: [p, p + NEXT) is exactly p


# ---------------------------------------------------------------------------
# Corpus and callers
# ---------------------------------------------------------------------------


def corpus(tops: int, folders: int, files: int) -> list[tuple[int, str, str | None]]:
    """``(id, path, owner)`` rows: tops, folders, files, and a ``-x`` sibling trap per top."""
    paths = ["/"]
    for t in range(tops):
        top = f"/t{t:02d}"
        paths.append(top)
        # "/t00/f000-x" sorts between "/t00/f000" and "/t00/f000/": a range that is
        # one piece instead of two would leak it.
        for name in [f"f{f:03d}" for f in range(folders)] + ["f000-x"]:
            paths.append(f"{top}/{name}")
            paths.extend(f"{top}/{name}/doc{n:03d}.md" for n in range(files))
    return [(i, p, "own" if p.endswith(".md") and i % 50 == 0 else None) for i, p in enumerate(paths)]


def callers(tops: int, folders: int) -> dict[str, Rights]:
    """Caller label → its resolved read rights, under a private root unless stated."""
    every = [f"/t{t:02d}/f{f:03d}" for t in range(tops) for f in range(folders)]

    def named(sub: str, prefixes: list[str]) -> Rights:
        rows = [GrantRow("*", ROOT, "none"), *(GrantRow(sub, p, "read") for p in prefixes)]
        return resolve({sub: frozenset()}, rows, "read")

    holes = [GrantRow("*", ROOT, "read"), *(GrantRow("*", p, "none") for p in every[::20])]
    return {
        "1 grant (10%)": named("a", ["/t00"]),
        "10 grants (1%)": named("b", every[:: max(1, len(every) // 10)]),
        "100 grants (10%)": named("c", every[:: max(1, len(every) // 100)]),
        f"{len(every) // 2} grants (50%)": named("d", every[::2]),
        f"open root, {len(holes) - 1} holes": resolve({"e": frozenset()}, holes, "read"),
        "10 grants + owns 2%": named("own", every[:: max(1, len(every) // 10)]),
    }


# ---------------------------------------------------------------------------
# Rights as sorted, disjoint byte ranges
# ---------------------------------------------------------------------------


class Pieces(NamedTuple):
    """Exact paths (``path = p``) and open ranges (``lo < path < hi``) that admit the same rows."""

    points: list[str]
    opens: list[tuple[str, str]]


def ranges(rights: Rights) -> tuple[Pieces, dict[str, Pieces]]:
    """The arms as pieces, and each owner arm's pieces by owner."""
    arms: list[tuple[str, str]] = []
    for arm in rights.arms:
        holes = [piece for hole in arm.holes for piece in _cover(hole)]
        arms.extend(_subtract(_cover(arm.prefix), holes))
    owners = {o.owner: _split(_merge([p for prefix in o.prefixes for p in _cover(prefix)])) for o in rights.owner_arms}
    return _split(_merge(arms)), owners


def _split(half_open: list[tuple[str, str]]) -> Pieces:
    """Half-open ``[lo, hi)`` ranges as exact points and open ranges.

    SQL Server pads the shorter string with spaces before comparing, so
    ``p < p + NEXT`` is false there: no bound may end in ``NEXT``, and an
    inclusive bound that is a lawful path becomes an exact point.
    """
    points: list[str] = []
    opens: list[tuple[str, str]] = []
    for lo, hi in half_open:
        if lo.endswith(NEXT):
            lo = lo[: -len(NEXT)]
        elif lo == ROOT or not lo.endswith("/"):
            points.append(lo)
        if hi.endswith(NEXT):
            hi = hi[: -len(NEXT)]
            if hi != lo:
                points.append(hi)
        if hi != lo:
            opens.append((lo, hi))
    return Pieces(points, opens)


def _cover(prefix: str) -> list[tuple[str, str]]:
    """The prefix row itself and everything beneath it, as two pieces (root is one)."""
    if prefix == ROOT:
        return [("/", "0")]
    return [(prefix, prefix + NEXT), (prefix + "/", prefix + "0")]


def _merge(pieces: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for lo, hi in sorted(pieces, key=lambda p: (p[0].encode(), p[1].encode())):
        if out and lo.encode() <= out[-1][1].encode():
            if hi.encode() > out[-1][1].encode():
                out[-1] = (out[-1][0], hi)
        else:
            out.append((lo, hi))
    return out


def _subtract(keep: list[tuple[str, str]], cut: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out = _merge(keep)
    for c_lo, c_hi in _merge(cut):
        cl, ch = c_lo.encode(), c_hi.encode()
        nxt: list[tuple[str, str]] = []
        for lo, hi in out:
            if ch <= lo.encode() or cl >= hi.encode():
                nxt.append((lo, hi))
                continue
            if lo.encode() < cl:
                nxt.append((lo, c_lo))
            if ch < hi.encode():
                nxt.append((c_hi, hi))
        out = nxt
    return out


# ---------------------------------------------------------------------------
# Per-dialect spellings of the range join
# ---------------------------------------------------------------------------


class Dialect:
    """The text an engine needs for one bound range list, a top-k, and a typed bind."""

    def __init__(self, name: str) -> None:
        self.name = name

    def source(self, key: str) -> tuple[str, str, str]:
        """``(FROM fragment, lo expr, hi expr)`` unpacking the bind *key*."""
        if self.name == "sqlite":
            return f"json_each(:{key}) AS {key}", f"{key}.value ->> 0", f"{key}.value ->> 1"
        if self.name == "postgresql":
            frag = f"unnest(CAST(:{key}_lo AS text[]), CAST(:{key}_hi AS text[])) AS {key}(lo, hi)"
            return frag, f'{key}.lo COLLATE "C"', f'{key}.hi COLLATE "C"'
        if self.name == "mssql":
            frag = f"OPENJSON(:{key}) WITH (lo varchar(1024) '$[0]', hi varchar(1024) '$[1]') AS {key}"
            return frag, f"{key}.lo COLLATE {MSSQL_UTF8_COLLATION}", f"{key}.hi COLLATE {MSSQL_UTF8_COLLATION}"
        cols = "COLUMNS (lo VARCHAR2(1024) PATH '$[0]', hi VARCHAR2(1024) PATH '$[1]')"
        if self.name == "oracle":
            return f"JSON_TABLE(:{key}, '$[*]' {cols}) {key}", f"{key}.lo", f"{key}.hi"
        cols = cols.replace("VARCHAR2", "VARCHAR")
        frag = f"JSON_TABLE(:{key}, '$[*]' {cols}) AS {key}"
        return frag, f"CAST({key}.lo AS BINARY)", f"CAST({key}.hi AS BINARY)"

    def binds(self, key: str, pieces: list[tuple[str, str]]) -> dict[str, Any]:
        if self.name == "postgresql":
            return {f"{key}_lo": [lo for lo, _ in pieces], f"{key}_hi": [hi for _, hi in pieces]}
        return {key: json.dumps(pieces)}

    def owner(self, key: str) -> str:
        return f"CAST(:{key} AS varchar(255))" if self.name == "mssql" else f":{key}"

    def top(self, sql_from_where: str, cols: str, order: str, k: int) -> str:
        if self.name == "mssql":
            return f"SELECT TOP {k} {cols} {sql_from_where} ORDER BY {order}"
        if self.name == "oracle":
            return f"SELECT {cols} {sql_from_where} ORDER BY {order} FETCH FIRST {k} ROWS ONLY"
        return f"SELECT {cols} {sql_from_where} ORDER BY {order} LIMIT {k}"


def join_statements(
    d: Dialect, entry: str, chunk: str, pieces: Pieces, owners: dict[str, Pieces], *, derived: bool = False
) -> dict[str, Any]:
    """The three range-join statements and their binds: one branch per bound list, merged by UNION.

    Chunks take their entries by ``entry_id IN (visible)``, or with
    *derived* by joining the visible entries as a derived table.
    """
    branches: list[str] = []
    params: dict[str, Any] = {}

    def branch(key: str, found: Pieces, where: str = "") -> None:
        nonlocal params
        if found.points:
            frag, lo, _ = d.source(f"{key}p")
            branches.append(f"SELECT e.id FROM {frag} JOIN {entry} e ON e.path = {lo}{where}")
            params |= d.binds(f"{key}p", [(p, p) for p in found.points])
        if found.opens:
            frag, lo, hi = d.source(f"{key}r")
            branches.append(f"SELECT e.id FROM {frag} JOIN {entry} e ON e.path > {lo} AND e.path < {hi}{where}")
            params |= d.binds(f"{key}r", found.opens)

    branch("a", pieces)
    for n, (owner, owned) in enumerate(owners.items()):
        branch(f"o{n}", owned, f" WHERE e.owner_id = {d.owner(f'w{n}')}")
        params[f"w{n}"] = owner
    visible = " UNION ".join(branches)
    if derived:
        where = f"FROM ({visible}) v JOIN {chunk} c ON c.entry_id = v.id"
    else:
        where = f"FROM {chunk} c WHERE c.entry_id IN ({visible})"
    stmts = {
        "entries": visible,
        "count": f"SELECT count(*) {where}",
        "top10": d.top(where, "c.id", "c.score", 10),
    }
    out: dict[str, Any] = {}
    for label, sql in stmts.items():
        stmt = text(sql)
        if d.name == "oracle":
            stmt = stmt.bindparams(*(bindparam(k, type_=CLOB) for k in params if not k.startswith("w")))
        out[label] = (stmt, params)
    return out


def literal_predicate(entry: Table, pieces: Pieces, owners: dict[str, Pieces]) -> Any:
    """ADR 072 rule 5: the same pieces inline as one OR."""

    def admitted(found: Pieces) -> list[Any]:
        exact = [entry.c.path.in_(found.points)] if found.points else []
        return exact + [and_(entry.c.path > lo, entry.c.path < hi) for lo, hi in found.opens]

    owned = [and_(entry.c.owner_id == o, or_(*admitted(found))) for o, found in owners.items()]
    return or_(*admitted(pieces), *owned)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


async def run(engine_name: str, tops: int, folders: int, files: int, reps: int) -> None:
    url = (
        f"sqlite+aiosqlite:///{os.path.join(HERE, f'rj-{uuid4().hex[:6]}.sqlite')}"
        if engine_name == "sqlite"
        else os.environ[ENGINE_ENV[engine_name]]
    )
    engine = create_async_engine(url, **({"use_setinputsizes": False} if engine_name == "mssql" else {}))
    if engine_name == "sqlite":
        event.listen(engine.sync_engine, "connect", lambda c, _: c.execute("PRAGMA case_sensitive_like = ON"))
    d = Dialect(engine.dialect.name)
    profile = profile_for(d.name)
    budget = engine.dialect.insertmanyvalues_max_parameters
    ns = f"rj_{uuid4().hex[:8]}"
    md = MetaData()
    ident = BigInteger().with_variant(Integer, "sqlite")
    owner_type = String(255).with_variant(String(255, collation=MSSQL_UTF8_COLLATION), "mssql")
    entry = Table(
        f"{ns}_e", md,
        Column("id", ident, primary_key=True, autoincrement=False),
        Column("path", BytewiseString(1024), nullable=False),
        Column("owner_id", owner_type),
    )
    chunk = Table(
        f"{ns}_c", md,
        Column("id", ident, primary_key=True, autoincrement=False),
        Column("entry_id", ident, nullable=False),
        Column("score", Integer, nullable=False),
    )
    Index(f"ux_{ns}_path", entry.c.path, unique=True)
    Index(f"ix_{ns}_owner", entry.c.owner_id)
    Index(f"ix_{ns}_ce", chunk.c.entry_id)
    Index(f"ix_{ns}_cs", chunk.c.score)

    rows = corpus(tops, folders, files)
    rng = random.Random(72)
    file_ids = [i for i, p, _ in rows if p.endswith(".md")]
    scores = rng.sample(range(len(file_ids) * CHUNKS_PER_FILE * 4), len(file_ids) * CHUNKS_PER_FILE)
    chunks = [(n, fid, scores[n]) for n, fid in enumerate(f for f in file_ids for _ in range(CHUNKS_PER_FILE))]
    lines: list[str] = []
    started = time.perf_counter()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(md.create_all)
        async with engine.begin() as conn:
            for i in range(0, len(rows), 5_000):
                await conn.execute(insert(entry), [{"id": a, "path": p, "owner_id": o} for a, p, o in rows[i : i + 5_000]])
            for i in range(0, len(chunks), 10_000):
                await conn.execute(insert(chunk), [{"id": a, "entry_id": b, "score": s} for a, b, s in chunks[i : i + 10_000]])
        async with engine.begin() as conn:
            await _analyze(conn, d.name, [entry.name, chunk.name])
        load_s = time.perf_counter() - started
        head = (f"## {engine_name} — {len(rows):,} entries, {len(chunks):,} chunks, loaded in {load_s:.0f}s, "
                f"median of {reps} warm runs (ms)\n")
        print(head, flush=True)
        lines += [head, "| caller | pieces | arms: clauses | statement | " + " | ".join(SHAPES) + " | recall "
                  + " / ".join(SHAPES) + " |", "|---|---|---|---|" + "---|" * (len(SHAPES) + 1)]
        joined = chunk.join(entry, entry.c.id == chunk.c.entry_id)
        score_of = {a: s for a, _, s in chunks}
        for label, rights in callers(tops, folders).items():
            exact_e = {a for a, p, o in rows if rights.admits(p, o)}
            exact_c = [a for a, b, _ in chunks if b in exact_e]
            exact = {
                "entries": exact_e,
                "count": len(exact_c),
                "top10": set(sorted(exact_c, key=score_of.__getitem__)[:10]),
            }
            pieces, owners = ranges(rights)
            n_pieces = sum(len(p.points) + len(p.opens) for p in (pieces, *owners.values()))
            clauses = visibility_clauses(entry, rights, profile, budget) or []
            literal_pred = literal_predicate(entry, pieces, owners)
            shapes: dict[str, dict[str, list[tuple[Any, dict]]]] = {
                "arms": {
                    "entries": [(select(entry.c.id).where(c.predicate), {}) for c in clauses],
                    "count": [(select(chunk.c.id).select_from(joined).where(c.predicate), {}) for c in clauses],
                    "top10": [(select(chunk.c.id).select_from(joined).where(c.predicate)
                               .order_by(chunk.c.score).limit(10), {}) for c in clauses],
                },
                "join IN": {k: [v] for k, v in join_statements(d, entry.name, chunk.name, pieces, owners).items()},
                "join derived": {
                    k: [v]
                    for k, v in join_statements(d, entry.name, chunk.name, pieces, owners, derived=True).items()
                },
            }
            if n_pieces <= LITERAL_MAX_PIECES:
                shapes["literal"] = {
                    "entries": [(select(entry.c.id).where(literal_pred), {})],
                    "count": [(select(func.count()).select_from(joined).where(literal_pred), {})],
                    "top10": [(select(chunk.c.id).select_from(joined).where(literal_pred)
                               .order_by(chunk.c.score).limit(10), {})],
                }
            for statement in ("entries", "count", "top10"):
                cells: dict[str, str] = {}
                recalls: dict[str, str] = {}
                for shape in SHAPES:
                    if shape not in shapes:
                        cells[shape], recalls[shape] = "—", "—"
                        continue
                    ms, got = await _time(engine, shapes[shape][statement], statement, shape, score_of, reps)
                    cells[shape] = ms
                    recalls[shape] = _recall(statement, got, exact[statement])
                times = " | ".join(cells[s] for s in SHAPES)
                recall = " / ".join(recalls[s] for s in SHAPES)
                row = f"| {label} | {n_pieces} | {len(clauses)} | {statement} | {times} | {recall} |"
                print(row, flush=True)
                lines.append(row)
        async with engine.connect() as conn:
            stmt, params = join_statements(d, entry.name, chunk.name, *ranges(callers(tops, folders)["100 grants (10%)"]))["count"]
            lines.append("\nPlan of the join's count statement, 100 grants:\n\n```\n" + await _plan(conn, d.name, stmt, params) + "\n```")
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(md.drop_all)
        await engine.dispose()
        if engine_name == "sqlite":
            os.remove(url.split("///", 1)[1])
    lines.append(f"\nTotal wall time {time.perf_counter() - started:.0f}s.")
    os.makedirs(os.path.join(HERE, "runs"), exist_ok=True)
    out = os.path.join(HERE, "runs", f"{engine_name}.md")
    with open(out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"→ {out}", flush=True)


async def _time(engine: Any, stmts: list, statement: str, shape: str, score_of: dict, reps: int) -> tuple[str, Any]:
    """Median ms over *reps* warm runs, and the first run's merged answer."""
    samples: list[float] = []
    answer: Any = None
    async with engine.connect() as conn:
        for r in range(reps + 1):
            t0 = time.perf_counter()
            try:
                answer = await _answer(conn, stmts, statement, shape, score_of)
            except Exception as exc:  # noqa: BLE001 — one failing spelling must not sink the run
                await conn.rollback()
                return f"error: {type(exc).__name__}: {str(exc).splitlines()[0][:80]}", None
            dt = time.perf_counter() - t0
            await conn.rollback()
            if r == 0:
                if dt > SLOW_CAP_S:
                    return f"{dt * 1000:,.0f} (1 run)", answer
                continue
            samples.append(dt * 1000)
    return f"{statistics.median(samples):,.1f}", answer


async def _answer(conn: AsyncConnection, stmts: list, statement: str, shape: str, score_of: dict) -> Any:
    ids: set[int] = set()
    count = 0
    for stmt, params in stmts:
        result = (await conn.execute(stmt, params)).all()
        if statement == "count" and shape != "arms":
            count += result[0][0]
        else:
            ids.update(row[0] for row in result)
    if statement == "count":
        return count if shape != "arms" else len(ids)
    if statement == "top10":
        return set(sorted(ids, key=score_of.__getitem__)[:10])
    return ids


def _recall(statement: str, got: Any, exact: Any) -> str:
    if got is None:
        return "error"
    if statement == "count":
        return "1.00" if got == exact else f"{got}≠{exact}"
    hit = len(got & exact) / len(exact) if exact else 1.0
    extra = len(got - exact)
    return f"{hit:.2f}" + (f" (+{extra} extra)" if extra else "")


async def _analyze(conn: AsyncConnection, dialect: str, names: list[str]) -> None:
    for n in names:
        sql = {
            "postgresql": f"ANALYZE {n}",
            "mssql": f"UPDATE STATISTICS {n} WITH FULLSCAN",
            "oracle": f"BEGIN DBMS_STATS.GATHER_TABLE_STATS(USER, '{n.upper()}', cascade => TRUE); END;",
            "mariadb": f"ANALYZE TABLE {n}",
            "sqlite": f"ANALYZE {n}",
        }[dialect]
        await conn.execute(text(sql))


async def _plan(conn: AsyncConnection, dialect: str, stmt: Any, params: dict) -> str:
    sql = stmt.text
    try:
        if dialect == "sqlite":
            rows = (await conn.execute(text("EXPLAIN QUERY PLAN " + sql), params)).all()
            return "\n".join(str(r[-1]) for r in rows)
        if dialect == "postgresql":
            rows = (await conn.execute(text("EXPLAIN ANALYZE " + sql), params)).all()
            return "\n".join(r[0] for r in rows)
        if dialect == "mariadb":
            rows = (await conn.execute(text("EXPLAIN " + sql), params)).mappings().all()
            return "\n".join(f"{r['select_type']} {r['table']} {r['type']} key={r['key']} rows={r['rows']} {r['Extra']}" for r in rows)
        if dialect == "oracle":
            sid = uuid4().hex[:12]
            clobs = (bindparam(k, type_=CLOB) for k in params if not k.startswith("w"))
            explain = text(f"EXPLAIN PLAN SET STATEMENT_ID = '{sid}' FOR " + sql).bindparams(*clobs)
            await conn.execute(explain, params)
            rows = (await conn.execute(text(f"SELECT plan_table_output FROM TABLE(DBMS_XPLAN.DISPLAY('PLAN_TABLE', '{sid}', 'BASIC ROWS'))"))).all()
            return "\n".join(r[0] for r in rows)
        if dialect == "mssql":
            await conn.execute(text("SET SHOWPLAN_TEXT ON"))
            try:
                result = await conn.execute(text(sql), params)
                return "\n".join(str(r[0]) for r in result.all())
            finally:
                await conn.execute(text("SET SHOWPLAN_TEXT OFF"))
    except Exception as exc:  # noqa: BLE001
        await conn.rollback()
        return f"plan unavailable: {type(exc).__name__}: {str(exc)[:200]}"
    return "?"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["sqlite", "postgres", "mssql", "oracle", "mariadb"])
    ap.add_argument("--tops", type=int, default=10)
    ap.add_argument("--folders", type=int, default=100)
    ap.add_argument("--files", type=int, default=20)
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    asyncio.run(run(a.engine, a.tops, a.folders, a.files, a.reps))
