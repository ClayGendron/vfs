"""Round-1 findings against the revision, by execution.

H1/H2: e5's extraction and decision 7's invert rule on round 1's own store (r02.db, files lower.c, upper.c, other.c).
M1/M5/L3: decision 3's probe on the path index alone, rows visited counted by a function in the WHERE clause.
M3: decision 4's refusal-first rule against today's database plan, and allow_scan parity of in hand and the scan tier.
L1: decision 8's bare round trip against real statements.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
import statistics
import sys
import time

from sqlalchemy import text

from vfs import AsyncVirtualFileSystem, DatabaseStorage
from vfs.models import Observation

R02, LINUX, E5 = sys.argv[1], sys.argv[2], sys.argv[3]
spec = importlib.util.spec_from_file_location("e5", E5)
e5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e5)
T = 1024


def h1_h2() -> None:
    raw = sqlite3.connect(f"file:{R02}?mode=ro", uri=True)
    expected = {"[Kk]malloc": {"/a/lower.c"}, "Kmalloc|kmalloc": {"/a/lower.c"}, "(?i)kmalloc": {"/a/lower.c", "/a/upper.c"},
                "(?i:KMALLOC)": {"/a/lower.c", "/a/upper.c"}}  # round-1 grep output, fmt: skip
    for pattern, rows in expected.items():
        lits = e5.required_literals(pattern, insensitive=False)
        if lits is None:
            kept = {p for (p,) in raw.execute("select path from vfs_entries where kind='file'")}
        else:
            where = " OR ".join("instr(c.content, ?) > 0" for _ in lits)
            kept = {p for (p,) in raw.execute("SELECT e.path FROM vfs_entries e JOIN vfs_content c ON "
                                              f"c.entry_id = e.entry_id WHERE {where}", sorted(lits))}
        print(f"H1 {pattern!r:20} e5 literals={lits} lost={sorted(rows - kept)}")
    print("H2 invert_match: decision 7 never runs the test under invert, so the scan side fetch is unfiltered: "
          f"rows kept = {sorted(p for (p,) in raw.execute('select path from vfs_entries where kind=?', ('file',)))}")


def m1_m5_l3() -> None:
    conn = sqlite3.connect(f"file:{LINUX}?mode=ro", uri=True)
    visits = [0]
    conn.create_function("visit", 1, lambda _: visits.__setitem__(0, visits[0] + 1) or 1)
    probe = "SELECT id, path FROM vfs_entries WHERE path > ? AND path < ? AND visit(id) LIMIT ?"
    print("M1 plan:", [r[-1] for r in conn.execute("EXPLAIN QUERY PLAN " + probe, ("/a/", "/a0", 5))])
    for root in ("/drivers/md", "/drivers/gpu", "/drivers"):
        visits[0] = 0
        rows = conn.execute(probe, (root + "/", root + "0", T + 1)).fetchall()
        ids = [i for i, _ in rows]
        marks = ",".join("?" * len(ids))
        dead = conn.execute(f"select count(*) from vfs_entries where id in ({marks}) and deleted_at is not null", ids).fetchone()[0]
        print(f"M1 {root:14} probe returned {len(rows)} visited {visits[0]}; trash side judged on them: {dead} tombstoned "
              f"-> verdict {'more than T' if len(rows) > T else 'n=' + str(len(rows))}")
    root = "/include/linux/dcache.h"
    n = len(conn.execute(probe, (root + "/", root + "0", T + 1)).fetchall()) + len(
        conn.execute("select id from vfs_entries where path = ?", (root,)).fetchall())
    print(f"M5 file root {root}: probe range rows + own row = {n}")
    roots = sorted({"/drivers", "/drivers/md", "/drivers/md/bcache"})
    maximal = [r for r in roots if not any(r.startswith(o + "/") for o in roots if o != r)]
    print(f"L3 roots {roots} reduce to {maximal}")


async def m3_l1() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{LINUX}")
    fs = AsyncVirtualFileSystem(storage=storage)
    raw = sqlite3.connect(f"file:{LINUX}?mode=ro", uri=True)
    try:
        for root in ("/mm/tests", "/drivers"):
            r = await fs.grep("a", paths=(root,), output_mode="files")
            print(f"M3 refusal-first: 'a' over {root}: {[e.kind.value for e in r.errors]}")
        root = "/kernel/kcsan"
        paths = [p for (p,) in raw.execute("select path from vfs_entries where kind='file' and path > ? and path < ?",
                                           (root + "/", root + "0"))]
        for pattern in ("^$", "x*", "."):
            db = await fs.grep(pattern, paths=(root,), allow_scan=True, output_mode="count")
            hand = await fs.grep(pattern, observations=[Observation(path=p, kind="file") for p in paths], output_mode="count")
            same = [(str(o.path), o.score) for o in db.observations] == [(str(o.path), o.score) for o in hand.observations]
            print(f"M3 allow_scan {pattern!r} over {root}: scan tier {len(db.observations)} rows, in hand "
                  f"{len(hand.observations)} rows, identical counts per file: {same}")
        bare, real = [], []
        async with storage.engine.connect() as conn:
            for _ in range(51):
                t0 = time.perf_counter()
                await conn.execute(text("SELECT 1"))
                bare.append((time.perf_counter() - t0) * 1000)
                t0 = time.perf_counter()
                await conn.execute(text("SELECT count(*) FROM vfs_entries WHERE path > '/drivers/' AND path < '/drivers0'"))
                real.append((time.perf_counter() - t0) * 1000)
        print(f"L1 SELECT 1 median {statistics.median(bare[1:]):.3f} ms (spread {min(bare[1:]):.3f}-{max(bare[1:]):.3f}); "
              f"a 40k-row count median {statistics.median(real[1:]):.3f} ms")
    finally:
        raw.close()
        await fs.close()


h1_h2()
m1_m5_l3()
asyncio.run(m3_l1())
