"""Decisions 2, 3 and 5 prototyped end to end: the probe on the index alone, the second probe, the four-way order.

Each call is planned as decision 5 orders it (T given on the command line), then run through vfs's own grep with
module functions replaced in this process; rows (paths, line spans, match text) are compared with today's code.
Counted exactly: rows each probe read, ids the candidate entry fetch resolved, statements.

    PYTHONPATH=<pinned src> uv run python r2_03_dispatch.py linux.db [T] [--time]
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import statistics
import sys
import time

from sqlalchemy import and_, event, or_

import vfs.storage.backends.database.backend as backend_module
import vfs.storage.backends.database.grep as g
from vfs import AsyncVirtualFileSystem, DatabaseStorage
from vfs.models import Observation

DB = sys.argv[1]
T = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 200
TIME = "--time" in sys.argv
BUDGET = g.SCAN_TIER_BUDGET
MODE = ["today"]
ALLOW: list[int] = []
ROOTS: list[str] = []
C: dict = {}
real_rows, real_push, real_entries, real_allow, real_defers = (backend_module.grep_rows, g.pushdown_terms,
                                                               g._entries_for_docs, g.allow_list_ids, g._ladder_defers)  # fmt: skip
real_ext = g.extension


class Rec:
    def __init__(self, r):
        self._r = r

    def __getattr__(self, n):
        return getattr(self._r, n)

    def candidate_ids(self, fed, allow, cap):
        ids, count = self._r.candidate_ids(fed, allow, cap)
        C["U"] = count
        return ids, count


async def grep_rows(*a, **k):
    ROOTS[:] = [str(r) for r in k["scope"].live] if k.get("scope") else []
    return await real_rows(*a, **k)


async def allow(*a, **k):
    if MODE[0] == "today":
        return await real_allow(*a, **k)
    return None if MODE[0] == "ranged" else list(ALLOW)


def push(entry, *a, **k):
    pd = real_push(entry, *a, **k)
    if MODE[0] != "ranged":
        return pd
    rng = or_(*(or_(entry.c.path == r, and_(entry.c.path > r + "/", entry.c.path < r + "0")) for r in ROOTS))
    return g.Pushdown((*pd.terms, rng), pd.binds + 3 * len(ROOTS))


async def entries(session, tables, profile, mb, doc_ids, fetched, pushdown):
    C["resolved"] = C.get("resolved", 0) + len(doc_ids)
    return await real_entries(session, tables, profile, mb, doc_ids, fetched, pushdown)


backend_module.grep_rows, g.allow_list_ids, g.pushdown_terms, g._entries_for_docs = grep_rows, allow, push, entries
g._ladder_defers = lambda *a: MODE[0] == "today" and real_defers(*a)
g.extension = lambda: Rec(real_ext())


def maximal(roots):
    return [r for r in sorted(set(roots)) if not any(r.startswith(o + "/") for o in roots if o != r)]


def probe(raw, roots, limit):
    ids = []
    for r in roots:
        ids += [i for (i,) in raw.execute("SELECT id FROM vfs_entries WHERE path > ? AND path < ? LIMIT ?",
                                          (r + "/", r + "0", limit + 1))]
        ids += [i for (i,) in raw.execute("SELECT id FROM vfs_entries WHERE path = ?", (r,))]
    return ids


async def planned(fs, raw, roots, pattern, kw):
    roots = maximal(roots)
    C.clear()
    first = probe(raw, roots, T)
    C["probe_rows"] = len(first)
    if len(first) <= T:
        marks = ",".join("?" * len(first)) or "NULL"
        paths = [p for (p,) in raw.execute(f"SELECT path FROM vfs_entries WHERE id IN ({marks}) AND kind = 'file' "
                                           "AND deleted_at IS NULL", first)]
        C["plan"] = "in hand"
        return await fs.grep(pattern, observations=[Observation(path=p, kind="file") for p in sorted(paths)], **kw)
    second = probe(raw, roots, BUDGET)
    C["probe_rows"] += len(second)
    if len(second) <= BUDGET:
        MODE[0], ALLOW[:] = "allowed", sorted(second)
        C["plan"] = "allow-listed by range"
        return await fs.grep(pattern, paths=tuple(roots), **kw)
    MODE[0] = "ranged"
    r = await fs.grep(pattern, paths=tuple(roots), **kw)
    if C.get("U", 0) <= BUDGET:
        C["plan"] = "range-scoped"
        return r
    full = []
    for x in roots:
        full += [i for (i,) in raw.execute("SELECT id FROM vfs_entries WHERE (path > ? AND path < ?) OR path = ?",
                                           (x + "/", x + "0", x))]
    MODE[0], ALLOW[:] = "allowed", sorted(full)
    C["plan"], C["full_allow"] = "allow-listed in full", len(full)
    return await fs.grep(pattern, paths=tuple(roots), **kw)


def shape(r):
    return tuple((str(o.path), tuple((m.start, m.end, m.match) for m in (o.matches or ()))) for o in r.observations)


SCOPES = [("/drivers",), ("/arch", "/fs")]
_UNUSED = [("/mm/tests",), ("/drivers/atm",), ("/drivers/md",), ("/drivers/gpu/drm/amd/display/dc",), ("/drivers/media",),
          ("/drivers/gpu",), ("/drivers",), ("/drivers/atm", "/mm/tests", "/kernel/kcsan"), ("/drivers", "/drivers/md"),
          ("/include/linux/dcache.h",), ("/fs/open.c", "/fs/read_write.c"), ("/arch", "/fs")]  # fmt: skip
PATTERNS = [("^static int", {})]
_UNUSED2 = [("dentry_lru_isolate", {}), ("i_count", {}), ("-EINVAL", {}), ("^static int", {}), ("kmalloc|kfree", {}),
            ("(?i)todo", {}), ("todo", {"case_mode": "insensitive"}), ("\\bd_inode\\b", {})]  # fmt: skip


async def main() -> None:
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}")
    fs = AsyncVirtualFileSystem(storage=storage)
    n = [0]
    event.listen(storage.engine.sync_engine, "before_cursor_execute", lambda *_: n.__setitem__(0, n[0] + 1))
    raw = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        await fs.stat("/fs")
        if not TIME:
            diffs = 0
            for roots in SCOPES:
                for pattern, kw in PATTERNS:
                    MODE[0] = "today"
                    C.clear()
                    base = await fs.grep(pattern, paths=roots, **kw)
                    trunc_today = [e.message[:30] for e in base.errors]
                    before = n[0]
                    got = await planned(fs, raw, roots, pattern, kw)
                    same = shape(base) == shape(got)
                    diffs += not same
                    print("   today rows", len(base.observations), "subset of planned:", set(shape(base)) <= set(shape(got)))
                    print(f"{'SAME' if same else 'DIFF'} {str(roots):48} {pattern!r:22} {len(got.observations):5}r "
                          f"plan={C['plan']:22} probe_rows={C['probe_rows']:6} resolved={C.get('resolved', 0):6} "
                          f"U={C.get('U')} full={C.get('full_allow', '-')} stmts={n[0] - before} "
                          f"today_err={trunc_today} err={[e.message[:30] for e in got.errors]}", flush=True)
            print("pairs that differ from today:", diffs)
        else:
            print("load", os.getloadavg())
            for roots in [("/kernel/kcsan",), ("/fs/ext4",), ("/kernel/bpf",), ("/drivers/clocksource",), ("/drivers/net/wireless/ath/ath9k",), ("/net/ipv4",), ("/fs/btrfs",), ("/mm",), ("/drivers/md",),
                          ("/drivers/gpu/drm/amd/display/dc",)]:
                for pattern in ("dentry_lru_isolate", "-EINVAL"):
                    out = []
                    for plan_t in (10**9, 0):
                        global T
                        T = plan_t
                        times = []
                        for i in range(8):
                            t0 = time.perf_counter()
                            await planned(fs, raw, roots, pattern, {"output_mode": "lines"})
                            if i:
                                times.append((time.perf_counter() - t0) * 1000)
                        out.append(f"{C['plan']}={statistics.median(times):6.1f}ms")
                    print(f"{roots[0]:34} {pattern:20} " + "  ".join(out), f"load={os.getloadavg()[0]:.1f}", flush=True)
    finally:
        raw.close()
        await fs.close()


asyncio.run(main())
