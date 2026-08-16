"""Controls: which flavor of block is it, and can the closed-connection error reproduce?

C1: cold instance, first op on an UNRELATED path, during the window -> blocks?
    (yes = first-touch/meta-row flavor, independent of row locks)
C2: warm (pre-touched) instance, op on an unrelated path, during the window -> blocks?
    (no = op path never reads the meta row; block is first-touch-specific)
C3: warm instance, op on the DELETED subtree's rows, during the window -> blocks?
    (yes = generic reader-behind-writer row locking, second flavor)
C4: eight concurrent cold instances first-touching inside a 60s window ->
    any raw closed-connection / pool failures?
"""

import asyncio
import os
import time

from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import seams

URL = os.environ["VFS_TEST_MSSQL_URL"]


def brief(result):
    return f"success={result.success} errors={[(e.kind, e.message[:120]) for e in result.errors]}"


async def run_probe(coro, hold, tag):
    t0 = time.monotonic()
    task = asyncio.create_task(coro)
    done, pending = await asyncio.wait([task], timeout=hold - 2)
    if pending:
        print(f"  {tag}: BLOCKED through the hold", flush=True)
        return task, t0
    print(f"  {tag}: completed in {time.monotonic() - t0:.1f}s during hold — {brief(task.result())}", flush=True)
    return None, t0


async def main() -> None:
    warm = DatabaseStorage(url=URL, table_name="coldrepro")
    await warm.write(entries=[Entry(path=Path(f"/d/f{i}.txt"), content="x") for i in range(20)], parents=True)
    await warm.write(entries=[Entry(path=Path("/unrelated/u.txt"), content="y")], parents=True)

    bystander = DatabaseStorage(url=URL, table_name="coldrepro")
    await bystander.stat(path=Path("/"))  # pre-touch: warm rival, distinct pool

    pending_tasks: list[tuple[str, object, float]] = []

    async def handler() -> None:
        seams.clear("delete:post-collect")
        hold = 12.0
        cold_unrel = DatabaseStorage(url=URL, table_name="coldrepro")
        t, t0 = await run_probe(cold_unrel.stat(path=Path("/unrelated/u.txt")), hold=6, tag="C1 cold+unrelated")
        if t:
            pending_tasks.append(("C1", t, t0))
        t, t0 = await run_probe(bystander.stat(path=Path("/unrelated/u.txt")), hold=6, tag="C2 warm+unrelated")
        if t:
            pending_tasks.append(("C2", t, t0))
        t, t0 = await run_probe(bystander.read(path=Path("/d/f0.txt")), hold=6, tag="C3 warm+deleted-subtree")
        if t:
            pending_tasks.append(("C3", t, t0))

    seams.install("delete:post-collect", handler)
    try:
        deleted = await warm.delete(path=Path("/d"))
    finally:
        seams.clear("delete:post-collect")
    print(f"  rival delete: {brief(deleted)}", flush=True)
    for tag, task, t0 in pending_tasks:
        try:
            result = await asyncio.wait_for(task, timeout=60)
            print(f"  {tag} after release: {time.monotonic() - t0:.1f}s total — {brief(result)}", flush=True)
        except asyncio.TimeoutError:
            print(f"  {tag}: HARD HANG past release", flush=True)
            task.cancel()

    print("--- C4: 8 concurrent cold first-touches inside a 60s window ---", flush=True)
    await warm.write(entries=[Entry(path=Path(f"/d2/f{i}.txt"), content="x") for i in range(20)], parents=True)
    outcomes: list[str] = []

    async def storm_handler() -> None:
        seams.clear("delete:post-collect")
        colds = [DatabaseStorage(url=URL, table_name="coldrepro") for _ in range(8)]
        t0 = time.monotonic()
        tasks = [asyncio.create_task(c.stat(path=Path("/unrelated/u.txt"))) for c in colds]
        done, pending = await asyncio.wait(tasks, timeout=60)
        outcomes.append(f"during hold: {len(done)} done, {len(pending)} blocked")
        for c in colds:
            pass  # closed after release below via gc; keep simple
        storm_handler.tasks = tasks  # type: ignore[attr-defined]
        storm_handler.t0 = t0  # type: ignore[attr-defined]

    seams.install("delete:post-collect", storm_handler)
    try:
        deleted = await warm.delete(path=Path("/d2"))
    finally:
        seams.clear("delete:post-collect")
    print(f"  rival delete: {brief(deleted)}", flush=True)
    tasks = getattr(storm_handler, "tasks", [])
    t0 = getattr(storm_handler, "t0", time.monotonic())
    results = await asyncio.gather(*tasks, return_exceptions=True)
    fails = [r for r in results if isinstance(r, BaseException) or not r.success]
    print(f"  {outcomes} | after release: {len(results)} finished, {time.monotonic() - t0:.1f}s total", flush=True)
    for r in fails:
        print(f"    FAIL: {r if isinstance(r, BaseException) else brief(r)}", flush=True)
    if not fails:
        print("    all eight classified clean (no raw closed-connection failures)", flush=True)
    await warm.close()
    await bystander.close()


asyncio.run(main())
