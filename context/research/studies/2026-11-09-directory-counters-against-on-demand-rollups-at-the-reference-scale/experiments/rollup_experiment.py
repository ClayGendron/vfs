"""Directory counters against on-demand subtree rollups, at the reference deployment's shape.

Builds a synthetic tree shaped like the reference deployment in AGENTS.md (one directory per
ten files, a two-file median directory with a long tail, depth around six with a tail past
twelve, a 4 KB median file) in the experiment's own tables, then measures three ways of
answering "how big is this directory":

- ondemand:  one GROUP BY over the subtree, bucketed by the child at depth one (no counters).
- direct:    one counter row per directory holding its direct children (JuiceFS's dirStats).
             A recursive read sums the counter rows under the root.
- recursive: one counter row per directory holding its whole subtree (CephFS's rstat).
             A read is the depth-one children's rows; a write touches every ancestor.

For each shape it counts statements issued, rows inserted, counter rows touched and rows the
read must scan, and records wall clock as a fact. Nothing here touches vfs's own tables.

    uv run python -I rollup_experiment.py --url sqlite+aiosqlite:////tmp/x.db --files 1000000 --out out.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from sqlalchemy import (
    BigInteger,
    Column,
    Identity,
    Integer,
    MetaData,
    String,
    Table,
    bindparam,
    case,
    event,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = "/corp"
SEED = 20261109
PATH_LEN = 512
COUNTER_CHUNK = 1000  # JuiceFS flushes directory stats in transactions of at most 1,000 rows
IN_BUDGET = 1000  # Oracle's IN-list cap, the floor vfs designs against


# ---------------------------------------------------------------------------
# Statement accounting
# ---------------------------------------------------------------------------


@dataclass
class Counter:
    statements: int = 0
    rows_bound: int = 0  # parameter sets across executemany calls
    log: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.statements = 0
        self.rows_bound = 0


def attach_counter(engine) -> Counter:
    counter = Counter()

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        counter.statements += 1
        if executemany:
            counter.rows_bound += len(parameters)
        else:
            counter.rows_bound += 1

    return counter


# ---------------------------------------------------------------------------
# Tree generation at the reference shape
# ---------------------------------------------------------------------------


@dataclass
class Tree:
    dir_paths: list[str]
    dir_parent: list[int]  # index into dir_paths, -1 for the root
    dir_depth: list[int]
    files_total: int
    direct_files: list[int]
    direct_dirs: list[int]
    direct_bytes: list[int]
    direct_lines: list[int]
    cum_weights: list[float]


def poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p < limit:
            return k
        k += 1


def file_size(rng: random.Random) -> int:
    # lognormal with a 4 KB median and a mean near 0.3 MB, capped at 1 GB
    return min(int(4096 * math.exp(rng.gauss(0.0, 2.9))), 1 << 30)


def build_dirs(rng: random.Random, n_dirs: int) -> Tree:
    """Directories first: depth from Poisson(4.4)+1 clipped to 14, parent drawn from the level above."""
    depths = [min(max(poisson(rng, 4.4) + 1, 1), 14) for _ in range(n_dirs)]
    order = sorted(range(n_dirs), key=depths.__getitem__)
    by_depth: dict[int, list[int]] = defaultdict(list)
    dir_paths = [""] * n_dirs
    dir_parent = [-1] * n_dirs
    dir_depth = [0] * n_dirs
    for i in order:
        d = depths[i]
        while d > 1 and not by_depth[d - 1]:
            d -= 1
        if d == 1:
            parent, parent_path = -1, ROOT
        else:
            parent = rng.choice(by_depth[d - 1])
            parent_path = dir_paths[parent]
        dir_paths[i] = f"{parent_path}/d{i}"
        dir_parent[i] = parent
        dir_depth[i] = d
        by_depth[d].append(i)
    # lognormal weights (sigma 1.8): a two-file median directory, a ten-file mean, a long tail
    weights = [math.exp(rng.gauss(0.0, 1.8)) for _ in range(n_dirs)]
    cum, acc = [], 0.0
    for w in weights:
        acc += w
        cum.append(acc)
    direct_dirs = [0] * n_dirs
    for i, p in enumerate(dir_parent):
        if p >= 0:
            direct_dirs[p] += 1
    return Tree(dir_paths, dir_parent, dir_depth, 0, [0] * n_dirs, direct_dirs, [0] * n_dirs, [0] * n_dirs, cum)


def file_rows(rng: random.Random, tree: Tree, start: int, count: int) -> list[dict]:
    """One chunk of file rows, their directory drawn from the Zipf weights; tallies the direct counters."""
    idxs = rng.choices(range(len(tree.dir_paths)), cum_weights=tree.cum_weights, k=count)
    rows = []
    for n, di in enumerate(idxs, start):
        size = file_size(rng)
        lines = max(size // 40, 1)
        parent = tree.dir_paths[di]
        rows.append(
            {
                "path": f"{parent}/f{n}.txt",
                "parent_path": parent,
                "kind": "file",
                "depth": tree.dir_depth[di] + 1,
                "size_bytes": size,
                "lines": lines,
            }
        )
        tree.direct_files[di] += 1
        tree.direct_bytes[di] += size
        tree.direct_lines[di] += lines
    tree.files_total += count
    return rows


def recursive_totals(tree: Tree) -> tuple[list[int], list[int], list[int], list[int]]:
    rf, rd, rb, rl = (
        list(tree.direct_files),
        list(tree.direct_dirs),
        list(tree.direct_bytes),
        list(tree.direct_lines),
    )
    for i in sorted(range(len(tree.dir_paths)), key=tree.dir_depth.__getitem__, reverse=True):
        p = tree.dir_parent[i]
        if p >= 0:
            rf[p] += rf[i]
            rd[p] += rd[i]
            rb[p] += rb[i]
            rl[p] += rl[i]
    return rf, rd, rb, rl


def ancestors(tree: Tree, di: int) -> list[str]:
    out = []
    while di >= 0:
        out.append(tree.dir_paths[di])
        di = tree.dir_parent[di]
    out.append(ROOT)
    return out


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

metadata = MetaData()
entries = Table(
    "exp_entries",
    metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True),
    Column("path", String(PATH_LEN), nullable=False, unique=True),
    Column("parent_path", String(PATH_LEN), nullable=False, index=True),
    Column("kind", String(8), nullable=False),
    Column("depth", Integer, nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("lines", Integer, nullable=False),
)
direct = Table(
    "exp_dir_direct",
    metadata,
    Column("path", String(PATH_LEN), primary_key=True),
    Column("files", Integer, nullable=False),
    Column("dirs", Integer, nullable=False),
    Column("bytes", BigInteger, nullable=False),
    Column("lines", BigInteger, nullable=False),
)
recursive = Table(
    "exp_dir_recursive",
    metadata,
    Column("path", String(PATH_LEN), primary_key=True),
    Column("parent_path", String(PATH_LEN), nullable=False, index=True),
    Column("rfiles", Integer, nullable=False),
    Column("rdirs", Integer, nullable=False),
    Column("rbytes", BigInteger, nullable=False),
    Column("rlines", BigInteger, nullable=False),
)


def segment_expr(dialect: str, prefix: str):
    """The child segment of ``path`` directly under ``prefix`` (which ends with a slash)."""
    rest = func.substr(entries.c.path, len(prefix) + 1) if dialect != "mssql" else func.substring(entries.c.path, len(prefix) + 1, PATH_LEN)
    if dialect == "postgresql":
        pos = func.strpos(rest, "/")
    elif dialect == "mssql":
        pos = func.charindex("/", rest)
    else:
        pos = func.instr(rest, "/")
    head = func.substr(rest, 1, pos - 1) if dialect != "mssql" else func.substring(rest, 1, pos - 1)
    return case((pos > 0, head), else_=rest)


def counter_segment_expr(dialect: str, prefix: str, col):
    rest = func.substr(col, len(prefix) + 1) if dialect != "mssql" else func.substring(col, len(prefix) + 1, PATH_LEN)
    if dialect == "postgresql":
        pos = func.strpos(rest, "/")
    elif dialect == "mssql":
        pos = func.charindex("/", rest)
    else:
        pos = func.instr(rest, "/")
    head = func.substr(rest, 1, pos - 1) if dialect != "mssql" else func.substring(rest, 1, pos - 1)
    return case((pos > 0, head), else_=rest)


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ---------------------------------------------------------------------------
# The runs
# ---------------------------------------------------------------------------


async def timed(coro):
    t0 = time.perf_counter()
    result = await coro
    return result, round((time.perf_counter() - t0) * 1000, 1)


async def bulk_insert(engine, table, rows, page):
    async with engine.begin() as conn:
        for chunk in chunks(rows, page):
            await conn.execute(insert(table), chunk)


async def seed(engine, counter, tree, n_files, page, results, rng):
    t0 = time.perf_counter()
    dir_rows = [
        {
            "path": p,
            "parent_path": tree.dir_paths[tree.dir_parent[i]] if tree.dir_parent[i] >= 0 else ROOT,
            "kind": "dir",
            "depth": tree.dir_depth[i],
            "size_bytes": 0,
            "lines": 0,
        }
        for i, p in enumerate(tree.dir_paths)
    ]
    dir_rows.insert(0, {"path": ROOT, "parent_path": "/", "kind": "dir", "depth": 0, "size_bytes": 0, "lines": 0})
    await bulk_insert(engine, entries, dir_rows, page)
    done = 0
    while done < n_files:
        count = min(100_000, n_files - done)
        await bulk_insert(engine, entries, file_rows(rng, tree, done, count), page)
        done += count
    results["seed"] = {
        "entry_rows": n_files + len(tree.dir_paths) + 1,
        "statements": counter.statements,
        "wall_ms": round((time.perf_counter() - t0) * 1000),
    }
    counter.reset()
    # direct counters from one GROUP BY: this is also the repair scan's cost
    async with engine.begin() as conn:
        t0 = time.perf_counter()
        sel = select(
            entries.c.parent_path,
            func.sum(case((entries.c.kind == "file", 1), else_=0)),
            func.sum(case((entries.c.kind == "dir", 1), else_=0)),
            func.sum(entries.c.size_bytes.cast(BigInteger)),
            func.sum(entries.c.lines.cast(BigInteger)),
        ).group_by(entries.c.parent_path)
        await conn.execute(insert(direct).from_select(["path", "files", "dirs", "bytes", "lines"], sel))
        results["repair_scan_direct"] = {
            "rows_scanned": results["seed"]["entry_rows"],
            "statements": counter.statements,
            "wall_ms": round((time.perf_counter() - t0) * 1000),
        }
    counter.reset()
    rf, rd, rb, rl = recursive_totals(tree)
    rrows = [
        {
            "path": p,
            "parent_path": tree.dir_paths[tree.dir_parent[i]] if tree.dir_parent[i] >= 0 else ROOT,
            "rfiles": rf[i],
            "rdirs": rd[i],
            "rbytes": rb[i],
            "rlines": rl[i],
        }
        for i, p in enumerate(tree.dir_paths)
    ]
    rrows.insert(
        0,
        {
            "path": ROOT,
            "parent_path": "/",
            "rfiles": sum(tree.direct_files),
            "rdirs": len(tree.dir_paths),
            "rbytes": sum(tree.direct_bytes),
            "rlines": sum(tree.direct_lines),
        },
    )
    t0 = time.perf_counter()
    await bulk_insert(engine, recursive, rrows, page)
    results["seed_recursive"] = {"rows": len(rrows), "statements": counter.statements, "wall_ms": round((time.perf_counter() - t0) * 1000)}
    counter.reset()
    return rf


async def read_rollups(engine, counter, dialect, tree, rf, results):
    """Depth-one rollups at the root and at a mid-tree directory holding about 1% of the files."""
    # the depth-2 directory whose subtree is nearest 1% of the files
    target = 0.01 * tree.files_total
    mid = min((i for i in range(len(tree.dir_paths)) if tree.dir_depth[i] == 2), key=lambda i: abs(rf[i] - target))
    for label, root, under in (("root", ROOT, tree.files_total + len(tree.dir_paths)), ("mid", tree.dir_paths[mid], rf[mid] + sum(1 for p in tree.dir_paths if p.startswith(tree.dir_paths[mid] + "/")))):
        prefix = root + "/"
        out = {"root": root, "entries_under": under}
        async with engine.connect() as conn:
            seg = segment_expr(dialect, prefix)
            inner = (
                select(seg.label("child"), entries.c.kind, entries.c.size_bytes)
                .where(entries.c.path.like(prefix + "%"))
                .subquery()
            )
            stmt = select(
                inner.c.child,
                func.sum(case((inner.c.kind == "file", 1), else_=0)),
                func.sum(inner.c.size_bytes.cast(BigInteger)),
            ).group_by(inner.c.child)
            counter.reset()
            rows, ms = await timed(conn.execute(stmt))
            out["ondemand"] = {"rows_scanned": under, "statements": counter.statements, "buckets": len(rows.all()), "wall_ms": ms}
            if dialect == "postgresql":
                plan = await conn.execute(text("EXPLAIN (ANALYZE, FORMAT TEXT) " + str(stmt.compile(conn.sync_connection.engine, compile_kwargs={"literal_binds": True}))))
                out["ondemand"]["plan"] = [r[0] for r in plan.all()][:6]
            cseg = counter_segment_expr(dialect, prefix, direct.c.path)
            dinner = select(cseg.label("child"), direct.c.files, direct.c.bytes).where(direct.c.path.like(prefix + "%")).subquery()
            dstmt = select(dinner.c.child, func.sum(dinner.c.files), func.sum(dinner.c.bytes)).group_by(dinner.c.child)
            dirs_under = sum(1 for p in tree.dir_paths if p.startswith(prefix))
            counter.reset()
            rows, ms = await timed(conn.execute(dstmt))
            out["direct"] = {"rows_scanned": dirs_under, "statements": counter.statements, "buckets": len(rows.all()), "wall_ms": ms}
            rstmt = select(recursive.c.path, recursive.c.rfiles, recursive.c.rbytes).where(recursive.c.parent_path == root)
            counter.reset()
            rows, ms = await timed(conn.execute(rstmt))
            n = len(rows.all())
            out["recursive"] = {"rows_scanned": n, "statements": counter.statements, "buckets": n, "wall_ms": ms}
        results[f"read_{label}"] = out


async def apply_direct(conn, deltas):
    """deltas: {parent_path: (dfiles, ddirs, dbytes, dlines)} coalesced; 1,000 rows a statement."""
    params = [{"p": p, "df": d[0], "dd": d[1], "db": d[2], "dl": d[3]} for p, d in deltas.items()]
    stmt = (
        update(direct)
        .where(direct.c.path == bindparam("p"))
        .values(
            files=direct.c.files + bindparam("df"),
            dirs=direct.c.dirs + bindparam("dd"),
            bytes=direct.c.bytes + bindparam("db"),
            lines=direct.c.lines + bindparam("dl"),
        )
    )
    for chunk in chunks(params, COUNTER_CHUNK):
        await conn.execute(stmt, chunk)
    return len(params)


async def apply_recursive(conn, deltas):
    params = [{"p": p, "df": d[0], "dd": d[1], "db": d[2], "dl": d[3]} for p, d in deltas.items()]
    stmt = (
        update(recursive)
        .where(recursive.c.path == bindparam("p"))
        .values(
            rfiles=recursive.c.rfiles + bindparam("df"),
            rdirs=recursive.c.rdirs + bindparam("dd"),
            rbytes=recursive.c.rbytes + bindparam("db"),
            rlines=recursive.c.rlines + bindparam("dl"),
        )
    )
    for chunk in chunks(params, COUNTER_CHUNK):
        await conn.execute(stmt, chunk)
    return len(params)


EDIT_STMT = update(entries).where(entries.c.id == bindparam("i")).values(size_bytes=bindparam("s"), lines=bindparam("l"))


def coalesce(tree, per_parent_idx: dict[int, list[int]], recursive_: bool) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for di, d in per_parent_idx.items():
        targets = ancestors(tree, di) if recursive_ else [tree.dir_paths[di]]
        for t in targets:
            acc = out[t]
            for k in range(4):
                acc[k] += d[k]
    return out


async def write_batches(engine, counter, tree, rng, page, results, batch=10_000):
    n_dirs = len(tree.dir_paths)
    shapes = {}
    # ingest, spread: 10,000 new files into existing directories drawn like the corpus
    idxs = rng.choices(range(n_dirs), cum_weights=tree.cum_weights, k=batch)
    rows, per_parent = [], defaultdict(lambda: [0, 0, 0, 0])
    for n, di in enumerate(idxs):
        size = file_size(rng)
        rows.append({"path": f"{tree.dir_paths[di]}/ingest_s{n}.txt", "parent_path": tree.dir_paths[di], "kind": "file", "depth": tree.dir_depth[di] + 1, "size_bytes": size, "lines": size // 40 + 1})
        d = per_parent[di]
        d[0] += 1
        d[2] += size
        d[3] += size // 40 + 1
    shapes["ingest_spread"] = (rows, per_parent)
    # ingest, concentrated: 10,000 new files into one existing shallow directory
    di = next(i for i in range(n_dirs) if tree.dir_depth[i] == 1)
    rows, per_parent = [], defaultdict(lambda: [0, 0, 0, 0])
    for n in range(batch):
        size = file_size(rng)
        rows.append({"path": f"{tree.dir_paths[di]}/ingest_c{n}.txt", "parent_path": tree.dir_paths[di], "kind": "file", "depth": 2, "size_bytes": size, "lines": size // 40 + 1})
        d = per_parent[di]
        d[0] += 1
        d[2] += size
        d[3] += size // 40 + 1
    shapes["ingest_concentrated"] = (rows, per_parent)

    for label, (rows, per_parent) in shapes.items():
        out = {"files": len(rows), "distinct_parents": len(per_parent)}
        async with engine.begin() as conn:
            counter.reset()
            _, ms = await timed(bulk_insert_conn(conn, rows, page))
            out["insert"] = {"statements": counter.statements, "rows": len(rows), "wall_ms": ms}
            counter.reset()
            deltas = coalesce(tree, per_parent, recursive_=False)
            n, ms = await timed(apply_direct(conn, deltas))
            out["direct_counters"] = {"statements": counter.statements, "counter_rows_touched": n, "wall_ms": ms}
            counter.reset()
            deltas = coalesce(tree, per_parent, recursive_=True)
            n, ms = await timed(apply_recursive(conn, deltas))
            out["recursive_counters"] = {"statements": counter.statements, "counter_rows_touched": n, "wall_ms": ms}
        results[f"write_{label}"] = out

    # edit, spread: 10,000 existing files re-sized (the nightly batch's shape), read-then-write
    out = {"files": batch}
    first_file_id = len(tree.dir_paths) + 2  # directories were inserted first, root included
    ids = rng.sample(range(first_file_id, first_file_id + tree.files_total), batch)
    async with engine.begin() as conn:
        counter.reset()
        t0 = time.perf_counter()
        found = []
        for chunk in chunks(ids, IN_BUDGET):
            res = await conn.execute(select(entries.c.id, entries.c.parent_path, entries.c.size_bytes, entries.c.lines).where(entries.c.id.in_(chunk)).where(entries.c.kind == "file"))
            found.extend(res.all())
        out["read_before_write"] = {"statements": counter.statements, "rows": len(found), "wall_ms": round((time.perf_counter() - t0) * 1000, 1)}
        counter.reset()
        t0 = time.perf_counter()
        params, per_parent_path = [], defaultdict(lambda: [0, 0, 0, 0])
        for rid, parent, size, lines in found:
            new_size = file_size(rng)
            new_lines = new_size // 40 + 1
            params.append({"i": rid, "s": new_size, "l": new_lines})
            d = per_parent_path[parent]
            d[2] += new_size - size
            d[3] += new_lines - lines
        for chunk in chunks(params, COUNTER_CHUNK):
            await conn.execute(EDIT_STMT, chunk)
        out["update"] = {"statements": counter.statements, "rows": len(params), "wall_ms": round((time.perf_counter() - t0) * 1000, 1)}
        out["distinct_parents"] = len(per_parent_path)
        path_to_idx = {p: i for i, p in enumerate(tree.dir_paths)}
        per_parent_idx = {path_to_idx[p]: d for p, d in per_parent_path.items()}
        counter.reset()
        n, ms = await timed(apply_direct(conn, coalesce(tree, per_parent_idx, False)))
        out["direct_counters"] = {"statements": counter.statements, "counter_rows_touched": n, "wall_ms": ms}
        counter.reset()
        n, ms = await timed(apply_recursive(conn, coalesce(tree, per_parent_idx, True)))
        out["recursive_counters"] = {"statements": counter.statements, "counter_rows_touched": n, "wall_ms": ms}
    results["write_edit_spread"] = out

    # a single agent edit: the daytime write
    out = {}
    rid = rng.randrange(first_file_id, first_file_id + tree.files_total)
    async with engine.begin() as conn:
        counter.reset()
        row = (await conn.execute(select(entries.c.id, entries.c.parent_path, entries.c.size_bytes, entries.c.lines).where(entries.c.id == rid))).one()
        new_size = file_size(rng)
        await conn.execute(EDIT_STMT, {"s": new_size, "l": new_size // 40 + 1, "i": rid})
        out["baseline"] = {"statements": counter.statements}
        di = tree.dir_paths.index(row.parent_path)
        delta = {di: [0, 0, new_size - row.size_bytes, new_size // 40 + 1 - row.lines]}
        counter.reset()
        n, ms = await timed(apply_direct(conn, coalesce(tree, delta, False)))
        out["direct_counters"] = {"statements": counter.statements, "counter_rows_touched": n, "wall_ms": ms}
        counter.reset()
        n, ms = await timed(apply_recursive(conn, coalesce(tree, delta, True)))
        out["recursive_counters"] = {"statements": counter.statements, "counter_rows_touched": n, "depth": tree.dir_depth[di], "wall_ms": ms}
    results["write_single_edit"] = out


async def bulk_insert_conn(conn, rows, page):
    for chunk in chunks(rows, page):
        await conn.execute(insert(entries), chunk)


RESTART_MARKERS = ("1020", "1213", "40001", "40P01", "ORA-08177", "ORA-00060", "1205", "3960")


def is_restart(exc: Exception) -> bool:
    msg = str(exc)
    return any(marker in msg for marker in RESTART_MARKERS)


async def contention(engine, tree, rng, results, workers=16, edits=50, max_restarts=1000):
    """Concurrent single-file edits in separate transactions: baseline, direct counters, recursive counters.

    A transaction the engine refuses as a serialization or snapshot conflict is restarted, and the
    restarts are counted: on MariaDB 11.6+ two increments of one counter row under snapshot isolation
    surface as error 1020 rather than as a lock wait."""
    out = {"workers": workers, "edits_per_worker": edits}
    first_file_id = len(tree.dir_paths) + 2
    ids_per_worker = [rng.sample(range(first_file_id, first_file_id + tree.files_total), edits) for _ in range(workers)]
    path_to_idx = {p: i for i, p in enumerate(tree.dir_paths)}
    restarts = {"baseline": 0, "direct": 0, "recursive": 0}

    async def one_edit(rid, mode):
        async with engine.begin() as conn:
            row = (await conn.execute(select(entries.c.id, entries.c.parent_path, entries.c.size_bytes, entries.c.lines).where(entries.c.id == rid))).one()
            new_size = file_size(rng)
            await conn.execute(EDIT_STMT, {"s": new_size, "l": new_size // 40 + 1, "i": rid})
            if mode == "baseline":
                return
            delta = {path_to_idx[row.parent_path]: [0, 0, new_size - row.size_bytes, new_size // 40 + 1 - row.lines]}
            if mode == "direct":
                await apply_direct(conn, coalesce(tree, delta, False))
            else:
                await apply_recursive(conn, coalesce(tree, delta, True))

    async def worker(ids, mode):
        for rid in ids:
            for attempt in range(max_restarts):
                try:
                    await one_edit(rid, mode)
                    break
                except Exception as exc:  # noqa: BLE001 - the restart markers decide
                    if not is_restart(exc) or attempt == max_restarts - 1:
                        raise
                    restarts[mode] += 1
                    await asyncio.sleep(0.001 * min(attempt + 1, 50))

    for mode in ("baseline", "direct", "recursive"):
        t0 = time.perf_counter()
        await asyncio.gather(*(worker(ids, mode) for ids in ids_per_worker))
        wall = time.perf_counter() - t0
        out[mode] = {"wall_ms": round(wall * 1000), "edits_per_second": round(workers * edits / wall, 1), "restarts": restarts[mode]}
    results["contention"] = out


def describe_tree(tree, rf) -> dict:
    files = sorted(tree.direct_files)
    n = len(files)
    depths = tree.dir_depth
    return {
        "directories": n,
        "files": tree.files_total,
        "files_per_dir_mean": round(tree.files_total / n, 2),
        "files_per_dir_median": files[n // 2],
        "files_per_dir_p99": files[int(n * 0.99)],
        "files_per_dir_max": files[-1],
        "dirs_with_no_files_share": round(sum(1 for f in files if f == 0) / n, 3),
        "depth_mean": round(sum(depths) / n, 2),
        "depth_max": max(depths),
        "depth_ge8_share": round(sum(1 for d in depths if d >= 8) / n, 3),
        "root_children": sum(1 for d in depths if d == 1),
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--files", type=int, default=1_000_000)
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-contention", action="store_true")
    ap.add_argument("--max-restarts", type=int, default=1000)
    args = ap.parse_args()
    rng = random.Random(SEED)
    if args.url.startswith("sqlite"):
        engine = create_async_engine(args.url)
    elif args.url.startswith("mssql"):
        # aioodbc runs every blocking ODBC call on a thread; the loop's default pool (cpu+4 threads) is
        # smaller than 16 workers, so a lock holder could starve of a thread to commit on. Give it room.
        engine = create_async_engine(args.url, pool_size=20, max_overflow=0, connect_args={"executor": ThreadPoolExecutor(max_workers=64)})
    else:
        engine = create_async_engine(args.url, pool_size=20, max_overflow=0)
    counter = attach_counter(engine)
    dialect = engine.dialect.name
    page_params = engine.dialect.insertmanyvalues_max_parameters or 32_000
    page = max(1, min(page_params // 6, 2000))
    results = {"url": args.url.split("@")[-1], "dialect": dialect, "files_requested": args.files, "insert_page_rows": page, "counter_chunk_rows": COUNTER_CHUNK}
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
    tree = build_dirs(rng, max(args.files // 10, 10))
    def save():
        with open(args.out, "w") as fh:
            json.dump(results, fh, indent=1, default=str)

    rf = await seed(engine, counter, tree, args.files, page, results, rng)
    results["tree"] = describe_tree(tree, rf)
    save()
    await read_rollups(engine, counter, dialect, tree, rf, results)
    save()
    await write_batches(engine, counter, tree, rng, page, results)
    save()
    if not args.skip_contention and dialect != "sqlite":
        await contention(engine, tree, rng, results, max_restarts=args.max_restarts)
        save()
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
    await engine.dispose()
    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=1, default=str)
    print(json.dumps({k: v for k, v in results.items() if k in ("dialect", "tree", "read_root", "read_mid", "write_single_edit", "contention")}, indent=1, default=str))


if __name__ == "__main__":
    asyncio.run(main())
