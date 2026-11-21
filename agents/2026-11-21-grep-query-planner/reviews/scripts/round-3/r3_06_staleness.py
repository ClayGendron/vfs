"""Staleness: a rival write and an index publish committed mid-grep, after the pointer read and before the probe.

On a copy of r3_04's store. For each plan mode of r3_04, a rival on a second storage over the same file writes a new
matching file in scope, overwrites a matching file so it no longer matches, deletes a third, and rebuilds (publishes).
The grep's rows are compared with the rows a plain grep read just before the rival (the snapshot the call began on)
and just after it. A plan that reads no index generation must still return one snapshot's rows.

    PYTHONPATH=<pinned src> uv run python r3_06_staleness.py r3_04.db work.db
"""

from __future__ import annotations

import asyncio
import shutil
import sys

import r3_04_view_trash_meta as plans  # noqa: F401  (installs the plan prototypes; argv is re-pointed below)
from vfs import AsyncVirtualFileSystem, Authority, DatabaseStorage, Entry
from vfs.storage.backends.database import seams

SYSTEM = Authority.system()


def shape(r):
    return tuple((str(o.path), tuple((m.start, m.end, m.match) for m in (o.matches or ()))) for o in r.observations)


async def main(src: str, work: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        try:
            shutil.copy(src + suffix, work + suffix)
        except FileNotFoundError:
            pass
    fs = AsyncVirtualFileSystem(storage=DatabaseStorage(url=f"sqlite+aiosqlite:///{work}"))
    rival_storage = DatabaseStorage(url=f"sqlite+aiosqlite:///{work}")
    rival = AsyncVirtualFileSystem(storage=rival_storage)
    plans.RAW.append(__import__("sqlite3").connect(f"file:{work}?mode=ro", uri=True))
    try:
        for n, mode in enumerate(("today", "inhand", "allowrange", "ranged")):
            plans.MODE[0] = "today"
            before = await fs.grep("lock", paths=("/pub/late",), authority=SYSTEM)
            hits = [str(o.path) for o in before.observations]

            async def rival_commit(n=n, hits=hits) -> None:
                seams.clear("grep:after-pointer-read")
                w = await rival.write(
                    entries=[
                        Entry(path=f"/pub/late/rival_{n}.c", content="spin_lock(&rival);\n"),
                        Entry(path=hits[0], content="no match here\n"),
                    ],
                    authority=SYSTEM,
                )
                d = await rival.delete(path=hits[1], authority=SYSTEM)
                rb = await rival_storage.rebuild()
                print(f"   rival: write {w.success}, delete {d.success}, rebuild {rb.success}")

            seams.install("grep:after-pointer-read", rival_commit)
            plans.MODE[0] = mode
            try:
                during = await fs.grep("lock", paths=("/pub/late",), authority=SYSTEM)
                err = [e.message[:60] for e in during.errors]
            except Exception as exc:  # noqa: BLE001
                during, err = None, [f"raised {type(exc).__name__}: {exc}"]
            seams.clear("grep:after-pointer-read")
            plans.MODE[0] = "today"
            after = await fs.grep("lock", paths=("/pub/late",), authority=SYSTEM)
            got = None if during is None else shape(during)
            print(
                f"{mode:10} before {len(before.observations)} during {None if during is None else len(during.observations)} "
                f"after {len(after.observations)}  during==before {got == shape(before)}  during==after {got == shape(after)}"
                f"  errors {err}"
            )
    finally:
        await fs.close()
        await rival.close()


asyncio.run(main(sys.argv[1], sys.argv[2]))
