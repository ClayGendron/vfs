"""Decisions 1, 2, 4 and 5 prototyped on the sandbox: do the plans return the same rows, and which costs what?

Plans, each run through vfs's own grep with module functions replaced in this process (no source edited):
  today   : the pinned code, paths= scope.
  d1      : decision 1 alone - a fully literal allow-list arm resolves by `path = :pattern`.
  range   : decision 4's range-scoped ladder - no allow-list; the candidate fetch carries
            `path = root OR (path > root||'/' AND path < root||'0')` per root as pushdown.
  inhand  : decision 4's in-hand plan - the range probe (root row included) handed to grep(observations=...).
Rows are compared with line numbers and match text. Statement counts are exact; times are medians of warm runs.

    PYTHONPATH=<pinned src> uv run python r04_plans.py linux.db [--time]
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import statistics
import sys
import time

from sqlalchemy import and_, event, or_, select

import vfs.storage.backends.database.backend as backend_module
import vfs.storage.backends.database.grep as g
import vfs.storage.backends.database.pathterms as pt
from vfs import AsyncVirtualFileSystem, DatabaseStorage
from vfs.models import Observation

DB = sys.argv[1]
TIME = "--time" in sys.argv
MODE = ["today"]
ROOTS: list[str] = []
SEEN: dict = {}

real_grep_rows = backend_module.grep_rows
real_allow = g.allow_list_ids
real_pushdown = g.pushdown_terms
real_arm_ids = pt._arm_ids
real_extension = g.extension


async def grep_rows(*a, **k):
    sc = k.get("scope")
    ROOTS[:] = [] if sc is None else [str(r) for r in sc.live]
    return await real_grep_rows(*a, **k)


async def allow(*a, **k):
    ids = None if MODE[0] == "range" else await real_allow(*a, **k)
    SEEN["allow"] = None if ids is None else len(ids)
    return ids


def pushdown(entry, *a, **k):
    pd = real_pushdown(entry, *a, **k)
    if MODE[0] != "range" or not ROOTS:
        return pd
    rng = or_(*(or_(entry.c.path == r, and_(entry.c.path > r + "/", entry.c.path < r + "0")) for r in ROOTS))
    return g.Pushdown((*pd.terms, rng), pd.binds + 3 * len(ROOTS))


async def arm_ids(session, tables, arm, counts):
    if MODE[0] == "d1" and not (set(arm.pattern) & set("*?[{\\")):
        return {row.id for row in await session.execute(select(tables.entry.c.id).where(tables.entry.c.path == arm.pattern))}
    return await real_arm_ids(session, tables, arm, counts)


class Rec:
    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def candidate_ids(self, fed, allow_ids, cap):
        ids, count = self._real.candidate_ids(fed, allow_ids, cap)
        SEEN["U"] = count
        return ids, count


backend_module.grep_rows = grep_rows
g.allow_list_ids = allow
g.pushdown_terms = pushdown
pt._arm_ids = arm_ids
g.extension = lambda: Rec(real_extension())

SCOPES = [("/mm/tests",), ("/drivers/atm",), ("/drivers/md",), ("/drivers/gpu/drm/amd/display/dc",),
          ("/include/linux/dcache.h",), ("/fs/open.c", "/fs/read_write.c"),
          ("/drivers/atm", "/mm/tests", "/kernel/kcsan"), ("/drivers/md", "/drivers/md/bcache")]  # fmt: skip
PATTERNS = [("i_count", {}), ("-EINVAL", {}), ("MODULE_LICENSE", {}), ("^static int", {}),
            ("kmalloc|kfree", {}), ("todo", {"case_mode": "insensitive"}), ("xyzzy_no_such_symbol_42", {}),
            ("return 0;", {}), ("\\bd_inode\\b", {})]  # fmt: skip
TIMED = [(("/drivers/gpu/drm/amd/display/dc",), "-EINVAL"), (("/drivers/gpu/drm/amd/display/dc",), "MODULE_LICENSE"),
         (("/drivers/gpu/drm/amd/display/dc",), "i_count"), (("/drivers/md",), "-EINVAL"),
         (("/drivers/md",), "i_count"), (("/drivers/atm",), "i_count"), (("/drivers/atm",), "-EINVAL")]  # fmt: skip


def probe(raw: sqlite3.Connection, roots: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for r in roots:
        out += [p for (p,) in raw.execute(
            "SELECT path FROM vfs_entries WHERE kind='file' AND deleted_at IS NULL AND "
            "(path = ? OR (path > ? AND path < ?))", (r, r + "/", r + "0"))]
    return sorted(set(out))


def shape(result) -> tuple:
    return tuple((str(o.path), tuple((m.start, m.end, m.match) for m in (o.matches or ()))) for o in result.observations)


async def run(fs, raw, mode, roots, pattern, kw):
    MODE[0] = mode
    SEEN.clear()
    if mode == "inhand":
        rows = [Observation(path=p, kind="file") for p in probe(raw, roots)]
        return await fs.grep(pattern, observations=rows, **kw)
    return await fs.grep(pattern, paths=roots, **kw)


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    fs = AsyncVirtualFileSystem(storage=storage)
    stmts = [0]
    event.listen(storage.engine.sync_engine, "before_cursor_execute", lambda *_: stmts.__setitem__(0, stmts[0] + 1))
    raw = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        await fs.stat("/fs")
        print("PARITY")
        for roots in ([] if TIME else SCOPES):
            for pattern, kw in PATTERNS:
                shapes, notes = {}, []
                for mode in ("today", "d1", "range", "inhand"):
                    before = stmts[0]
                    r = await run(fs, raw, mode, roots, pattern, kw)
                    trunc = [e.message[:40] for e in r.errors]
                    shapes[mode] = shape(r)
                    notes.append(f"{mode}:{len(r.observations)}r/{stmts[0]-before}s/allow={SEEN.get('allow')}/U={SEEN.get('U')}{'/ERR' + str(trunc) if trunc else ''}")
                same = len(set(shapes.values())) == 1
                comparable = SEEN.get("U") is None or True
                print(("SAME " if same else "DIFF ") + f"{roots} {pattern!r} {kw} :: " + " ".join(notes))
                if not same:
                    base = set(shapes["today"])
                    for mode, s in shapes.items():
                        if set(s) != base:
                            print(f"     {mode}: missing={sorted(p for p, _ in base - set(s))[:5]} extra={sorted(p for p, _ in set(s) - base)[:5]}")
        if TIME:
            print("TIMING (median of 7 warm runs, ms; load:", os.getloadavg(), ")")
            for roots, pattern in TIMED:
                line = []
                for mode in ("today", "d1", "range", "inhand"):
                    times = []
                    for i in range(8):
                        before = stmts[0]
                        t0 = time.perf_counter()
                        r = await run(fs, raw, mode, roots, pattern, {"output_mode": "lines"})
                        if i:
                            times.append((time.perf_counter() - t0) * 1000)
                        n = stmts[0] - before
                    line.append(f"{mode}={statistics.median(times):7.1f}ms/{n}s/U={SEEN.get('U')}")
                print(f"{roots[0]:36} {pattern:16} " + "  ".join(line), "load", os.getloadavg()[0])
    finally:
        raw.close()
        await fs.close()


asyncio.run(main())
