"""Probe 4: the same verbs on the same worlds under a server engine's IN-list budget, emulated on SQLite.

usage: probe_budget.py DATA_DIR IN_LIST_BUDGET N [N ...]
The profile is SQLite's with in_list_budget replaced (Oracle 1,000; SQL Server 2,000), the suite's
monkeypatch idiom; the parameter budget is SQLite's. Counts statements and binds per verb for ann.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import replace

from probe_compile import verbs
from world import DATA, Recorder

from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import engine as engine_module
from vfs.storage.backends.database.dialects import SQLITE

HERE = DATA
KEYS = ("ls /", "ls /home", "ls /shared", "glob /home/**", "glob /shared/**", "grep needle", "read own", "write own")


async def main() -> None:
    budget, *sizes = map(int, sys.argv[2:])
    profile = replace(SQLITE, in_list_budget=budget)
    engine_module.profile_for = lambda name: profile
    for caller in ("ann", "heavy"):
        for key in KEYS:
            line = []
            for n in sizes:
                storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{os.path.join(HERE, f'world-{n}.sqlite')}")
                rec = Recorder(storage)
                try:
                    call = verbs(caller)[key]
                    await call(storage)
                    result, rows = await rec.run(call(storage))
                finally:
                    await storage.close()
                line.append(f"N={n}: ok={result.success} stmts={len(rows)} maxbinds={max(b for _, b, _ in rows)}")
            print(f"in_list={budget} {caller:6} {key:16} | " + " | ".join(line))


asyncio.run(main())
