"""Probe 12: a posture change whose first relabel chunk fails — what the caller and every reader see, and what clears it.

usage: probe_stuck.py DATA_DIR N
On a copy of world-N, the relabel driver's first chunk raises a driver error (the suite's own
monkeypatch of Relabeller.step), so `posture("/home", "list")` commits its posture row and its mark and
stops. Then: the verb's answer, the marks table, ann's grep cost and answer, an unrelated posture call,
and the same again. Counts only.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys

from world import SYSTEM, Recorder, build, who

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import backend as backend_module


async def main() -> None:
    data, n = sys.argv[1], int(sys.argv[2])
    copy = os.path.join(data, f"stuck-{n}.sqlite")
    source = os.path.join(data, f"world-{n}.sqlite")
    if not os.path.exists(source):
        await (await build(f"sqlite+aiosqlite:///{source}", n)).close()
    shutil.copyfile(source, copy)
    storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{copy}")
    rec = Recorder(storage)
    host = storage._host
    original = backend_module.Relabeller.step

    async def boom(self, session):
        raise OperationalError("relabel", {}, Exception("disk full"))

    async def marks() -> list[str]:
        async with host.session_factory() as session:
            return list((await session.execute(select(host.tables.relabels.c.path_prefix))).scalars())

    async def ann_grep(label: str) -> None:
        await storage.grep(pattern="needle", authority=who("ann"))
        result, rows = await rec.run(storage.grep(pattern="needle", authority=who("ann")))
        print(f"  {label}: ann grep ok={result.success} rows={len(result.observations)} statements={len(rows)}")

    try:
        await ann_grep("steady")
        backend_module.Relabeller.step = boom
        failed = await storage.posture(path=Path("/home"), posture="list", authority=SYSTEM)
        backend_module.Relabeller.step = original
        print(
            f"  posture('/home', 'list') with its first chunk failing: success={failed.success} "
            f"errors={[(e.kind.value, e.retryable) for e in failed.errors]} "
            f"grants={[(g['path_prefix'], g['level']) for g in (failed.model_extra or {}).get('grants') or []]} "
            f"relabel={(failed.model_extra or {}).get('relabel')}"
        )
        print(f"  marks standing: {await marks()}")
        await ann_grep("stuck")
        await storage.close()
        storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{copy}")
        rec = Recorder(storage)
        host = storage._host
        print(f"  after close and reopen, marks standing: {await marks()}")
        await ann_grep("stuck, reopened")
        cleared = await storage.posture(path=Path("/shared/s000"), posture="none", authority=SYSTEM)
        print(f"  an unrelated posture('/shared/s000', 'none'): success={cleared.success} "
              f"relabel={(cleared.model_extra or {}).get('relabel')}")
        print(f"  marks standing: {await marks()}")
        await ann_grep("cleared")
    finally:
        await storage.close()


asyncio.run(main())
