"""Repro: cold DatabaseStorage first touch inside a rival's in-flight topology window (MSSQL).

Scenario A (block measurement): warm instance A freezes mid-delete at the
`delete:post-collect` seam (inside its serialized topology transaction).
While frozen, cold instance B issues its first op. We measure whether B
blocks, for how long, and how its outcome classifies once A releases.

Scenario B (long hold): same, but A holds the window well past driver
login/connect timeouts, hunting the raw "Attempt to use a closed
connection" failure from the 2026-07-25 campaign.
"""

import asyncio
import os
import time

from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import seams

URL = os.environ["VFS_TEST_MSSQL_URL"]


def show(tag, result, t0):
    err = [(e.kind, getattr(e, "retryable", None), e.message[:180]) for e in result.errors]
    print(f"  [{tag}] success={result.success} elapsed={time.monotonic() - t0:.1f}s errors={err}", flush=True)


async def scenario(hold_seconds: float, label: str) -> None:
    print(f"--- scenario: {label} (hold {hold_seconds}s) ---", flush=True)
    warm = DatabaseStorage(url=URL, table_name="coldrepro")
    seed = await warm.write(
        entries=[Entry(path=Path(f"/d/f{i}.txt"), content="x") for i in range(20)], parents=True
    )
    assert seed.success, seed.errors

    probe: dict[str, object] = {}

    async def handler() -> None:
        seams.clear("delete:post-collect")
        cold = DatabaseStorage(url=URL, table_name="coldrepro")
        t0 = time.monotonic()
        task = asyncio.create_task(cold.stat(path=Path("/d")))
        done, pending = await asyncio.wait([task], timeout=hold_seconds)
        probe["blocked_through_hold"] = bool(pending)
        if pending:
            print(f"  cold first op still blocked after {hold_seconds:.0f}s hold; releasing rival", flush=True)
        else:
            show("cold-op finished DURING rival hold", task.result(), t0)
        probe["task"], probe["t0"], probe["cold"] = task, t0, cold

    seams.install("delete:post-collect", handler)
    t_del = time.monotonic()
    try:
        deleted = await warm.delete(path=Path("/d"))
    finally:
        seams.clear("delete:post-collect")
    show("rival delete", deleted, t_del)

    task = probe.get("task")
    if task is not None and probe.get("blocked_through_hold"):
        try:
            result = await asyncio.wait_for(task, timeout=60)
            show("cold-op after release", result, probe["t0"])
        except asyncio.TimeoutError:
            print("  cold op STILL blocked 60s after rival release — hard hang", flush=True)
            task.cancel()
    # Second op on the now-touched cold instance: is it healthy after the ordeal?
    cold = probe.get("cold")
    if cold is not None:
        t0 = time.monotonic()
        show("cold-op second call", await cold.stat(path=Path("/")), t0)
        await cold.close()
    await warm.close()


async def main() -> None:
    await scenario(10.0, "short hold — block-and-release shape")
    await scenario(45.0, "long hold — past driver login/connect timeouts")


asyncio.run(main())
