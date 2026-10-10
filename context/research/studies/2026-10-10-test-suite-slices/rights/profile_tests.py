"""cProfile driver for the top rights/grants oracle tests.

Usage: uv run --no-sync python profile_tests.py <test_name> [param ...]
Prints: statements and transactions split by phase (replay vs questions),
cumulative time of the key functions, and the top entries by cumtime.
"""

from __future__ import annotations

import asyncio
import cProfile
import pstats
import sys
import time
from collections import Counter

from sqlalchemy import event
from sqlalchemy.engine import Engine

sys.path.insert(0, "/Users/claygendron/Git/Repos/vfs")

import tests.storage.database.test_rights as rights  # noqa: E402
import tests.storage.test_grants as grants  # noqa: E402
from tests.support.grant_worlds import LAYOUTS  # noqa: E402

COUNTS: Counter[str] = Counter()
TIMES: Counter[str] = Counter()
PHASE = ["questions"]


@event.listens_for(Engine, "before_cursor_execute")
def _count_stmt(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
    COUNTS[f"stmt:{PHASE[0]}"] += 1
    verb = statement.lstrip().split(None, 1)[0].upper()
    COUNTS[f"stmt:{PHASE[0]}:{verb}"] += 1


@event.listens_for(Engine, "begin")
def _count_begin(conn):  # noqa: ANN001
    COUNTS[f"txn:{PHASE[0]}"] += 1


_real_replay = rights._replay


async def _counted_replay(world):  # noqa: ANN001
    COUNTS["replay:calls"] += 1
    prev = PHASE[0]
    PHASE[0] = "replay"
    t0 = time.perf_counter()
    try:
        return await _real_replay(world)
    finally:
        PHASE[0] = prev
        TIMES["replay"] += time.perf_counter() - t0


rights._replay = _counted_replay

# Count verb calls on the storage class.
from vfs.storage.backends.database import DatabaseStorage  # noqa: E402

for verb in ("write", "grant", "posture", "add_member", "glob", "stat", "delete", "restore", "sweep", "copy", "move", "mkdir", "close"):
    real = getattr(DatabaseStorage, verb)

    def make(real, verb):  # noqa: ANN001
        async def wrapped(self, *a, **kw):  # noqa: ANN001
            COUNTS[f"verb:{PHASE[0]}:{verb}"] += 1
            t0 = time.perf_counter()
            try:
                return await real(self, *a, **kw)
            finally:
                TIMES[f"verb:{PHASE[0]}:{verb}"] += time.perf_counter() - t0

        return wrapped

    setattr(DatabaseStorage, verb, make(real, verb))


import tests.support.oracles.grants as oracle  # noqa: E402


def _timed(mod, name):  # noqa: ANN001
    real = getattr(mod, name)

    def wrapped(*a, **kw):  # noqa: ANN001
        COUNTS[f"oracle:{name}"] += 1
        t0 = time.perf_counter()
        try:
            return real(*a, **kw)
        finally:
            TIMES[f"oracle:{name}"] += time.perf_counter() - t0

    setattr(mod, name, wrapped)


for _n in ("_expected", "_expected_trash", "set_rank", "everyone_rank"):
    if hasattr(rights, _n):
        _timed(rights, _n)
_timed(grants, "set_rank")
_timed(grants, "everyone_rank")

_real_labels = rights._assert_labels


async def _timed_labels(storage, world):  # noqa: ANN001
    COUNTS["labels:calls"] += 1
    t0 = time.perf_counter()
    try:
        return await _real_labels(storage, world)
    finally:
        TIMES["labels"] += time.perf_counter() - t0


rights._assert_labels = _timed_labels

_real_init = DatabaseStorage.__init__


def _timed_init(self, *a, **kw):  # noqa: ANN001
    t0 = time.perf_counter()
    try:
        return _real_init(self, *a, **kw)
    finally:
        TIMES["storage.__init__"] += time.perf_counter() - t0


DatabaseStorage.__init__ = _timed_init


def main() -> None:
    name = sys.argv[1]
    params = [a for a in sys.argv[2:] if not a.startswith("--")]
    module = rights if hasattr(rights, name) else grants
    fn = getattr(module, name)
    args = []
    for p in params:
        if p in ("base", "siblings"):
            args.append(LAYOUTS[0] if p == "base" else LAYOUTS[1])
        elif p.isdigit():
            args.append(int(p))
        else:
            args.append(p)
    prof = cProfile.Profile()
    use_prof = "--noprof" not in sys.argv
    t0 = time.perf_counter()
    if use_prof:
        prof.enable()
    if asyncio.iscoroutinefunction(fn):
        asyncio.run(fn(*args))
    else:
        fn(*args)
    if use_prof:
        prof.disable()
    wall = time.perf_counter() - t0
    print(f"== {name} {params}: wall {wall:.2f}s (under cProfile)")
    for key in sorted(COUNTS):
        print(f"  {key:40s} {COUNTS[key]}")
    print("-- phase/verb wall times (s)")
    for key in sorted(TIMES, key=lambda k: -TIMES[k]):
        print(f"  {key:40s} {TIMES[key]:.3f}")
    if not use_prof:
        return
    stats = pstats.Stats(prof)
    stats.sort_stats("cumulative")
    print("-- key functions (cumtime, ncalls)")
    wanted = [
        "_replay", "random_world", "set_rank", "subject_rank", "everyone_rank", "closure", "_expected",
        "_expected_trash", "_assert_labels", "_authority", "admits", "resolve", "_first_touch", "ensure_ready",
        "_verify_or_provision", "_provision", "_probe_sqlite_vec", "__init__", "close", "dispose", "execute",
        "glob_rows", "stat_rows", "resolve_authority", "visibility_clauses", "relabel", "step",
    ]
    rows = []
    for (file, line, func), (cc, nc, tt, ct, callers) in stats.stats.items():
        if func in wanted or any(func == f"wrapped" for _ in [0]):
            rows.append((ct, nc, func, file.rsplit("/", 1)[-1], line))
    rows.sort(reverse=True)
    for ct, nc, func, file, line in rows[:60]:
        print(f"  {ct:8.3f}s {nc:8d}  {func:28s} {file}:{line}")
    print("-- top 35 by cumtime")
    stats.print_stats(35)


if __name__ == "__main__":
    main()
