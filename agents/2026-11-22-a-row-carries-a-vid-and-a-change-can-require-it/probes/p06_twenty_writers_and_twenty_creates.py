"""Twenty calls at once that each require one state of one path: how many land, on each engine.

Two tests the etag spec names rest on today's arbitration and guard:

- ``test_twenty_writers_that_require_one_etag_land_once``: twenty writes,
  each with a body of its own, that all require the same state of one
  file. Run here with ``if_versions``, the guard an etag will ride on.
- ``test_twenty_marked_creates_of_one_path_land_once``: twenty create-only
  writes of one path. Run here with ``if_absent=True``, the call-wide
  flag the mark is the per-entry form of. The spec's test also has each
  batch replace a file of its own; no call can mix the two today, so
  that half is not run.

It then runs decision 9's append: twenty appends to one file that all
require its version, where one must land, and twenty plain appends,
where all must. Last it prints whether every handle on the one database
read the same mount identity, which is the key of the mint.

Each caller is a storage object of its own on the one database, so the
twenty are twenty connections. The probe prints the count of each
outcome, the version the file ends at, and the engine errors the callers'
connections raised on the way (a serialization failure is a second run).

    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/probes/p06_twenty_writers_and_twenty_creates.py
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import TYPE_CHECKING, Any

from sqlalchemy import event

from harness import engines, run, storage_on
from vfs.models import Entry
from vfs.paths import Path

if TYPE_CHECKING:
    from vfs.results import Result
    from vfs.storage.backends.database import DatabaseStorage

CALLERS = 20


def outcome(result: Result) -> str:
    if result.success:
        return f"ok:{result.observations[0].status}"
    return ",".join(sorted({str(e.kind) + ("(retryable)" if e.retryable else "") for e in result.errors}))


async def one_engine(engine: str) -> None:
    async with storage_on(engine) as (storage, make_rival):
        target = Path("/d/hot.txt")
        await storage.mkdir(path=Path("/d"))
        assert (await storage.write(entries=[Entry(path=target, content="seed")])).success
        callers: list[DatabaseStorage] = [make_rival() for _ in range(CALLERS)]
        errors: Counter[str] = Counter()

        def on_error(context: Any) -> None:
            origin = context.original_exception
            errors[str(getattr(origin, "sqlstate", None) or getattr(origin, "sqlite_errorname", None))] += 1

        for caller in callers:
            await caller.stat(path=Path("/"))
            event.listen(caller._host.engine.sync_engine, "handle_error", on_error)

        results = await asyncio.gather(
            *(
                caller.write(entries=[Entry(path=target, content=f"body {i}")], if_versions={target: 1})
                for i, caller in enumerate(callers)
            )
        )
        final = (await storage.stat(path=target)).observations[0].version
        print(f"-- twenty writes that require version 1: {dict(Counter(map(outcome, results)))}")
        print(f"   the file ends at version {final}; engine errors on the way: {dict(errors) or 'none'}")
        data = Counter(str(e.data) for r in results for e in r.errors)
        print(f"   the data of the refusals: {dict(data)}")

        errors.clear()
        fresh = Path("/d/new.txt")
        created = await asyncio.gather(
            *(
                caller.write(entries=[Entry(path=fresh, content=f"create {i}")], if_absent=True)
                for i, caller in enumerate(callers)
            )
        )
        final = (await storage.stat(path=fresh)).observations[0].version
        print(f"-- twenty create-only writes of one path: {dict(Counter(map(outcome, created)))}")
        print(f"   the file ends at version {final}; engine errors on the way: {dict(errors) or 'none'}")
        named = Counter("names version and hash" if e.data and "content_hash" in e.data else str(e.data)
                        for r in created for e in r.errors)  # fmt: skip
        print(f"   the data of the refusals: {dict(named)}")

        # Decision 9, "An append": a rival appender waits on the row lock, then meets the new version.
        errors.clear()
        log = Path("/d/log.txt")
        assert (await storage.write(entries=[Entry(path=log, content="start\n")])).success
        guarded = await asyncio.gather(
            *(
                caller.write(entries=[Entry(path=log, content=f"line {i}\n")], append=True, if_versions={log: 1})
                for i, caller in enumerate(callers)
            )
        )
        row = (await storage.read(path=log)).observations[0]
        print(f"-- twenty appends that require version 1: {dict(Counter(map(outcome, guarded)))}")
        print(f"   the file ends at version {row.version} with {len((row.content or '').splitlines())} lines; "
              f"engine errors on the way: {dict(errors) or 'none'}")  # fmt: skip
        errors.clear()
        plain = await asyncio.gather(
            *(
                caller.write(entries=[Entry(path=log, content=f"plain {i}\n")], append=True)
                for i, caller in enumerate(callers)
            )
        )
        row = (await storage.read(path=log)).observations[0]
        print(f"-- twenty plain appends: {dict(Counter(map(outcome, plain)))}")
        print(f"   the file ends at version {row.version} with {len((row.content or '').splitlines())} lines; "
              f"engine errors on the way: {dict(errors) or 'none'}")  # fmt: skip
        print(f"   one mount identity across the {CALLERS + 1} handles: "
              f"{len({c._host.mount_identity for c in (*callers, storage)}) == 1}")  # fmt: skip


async def main() -> None:
    for engine in engines():
        print(f"== {engine}")
        await one_engine(engine)


if __name__ == "__main__":
    run(main, deadline=180.0)
