"""The guard and the claim each verb sends, read off the wire on each engine, with the statement count of each call.

The etag spec says no term and no statement is added: the comparison is
made in Python and the mutation statement each verb already sends names
the entry and the version. This probe records what ``write``, ``edit``,
``delete``, ``move`` and ``restore`` send today, at the storage seam as
the system actor, and prints for each call the count of statements, the
list of their verbs, and the ``WHERE`` of the first ``UPDATE`` on
``vfs_entries`` (the guard or the claim). It also records a ``write``
with a stale expected version, which the spec says costs the snapshot alone.

The texts are what the driver was handed, so on Postgres they are the
statements a server parsed, not a compilation of the builder.

    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/probes/p02_the_statements_the_builders_emit.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from harness import engines, recorded, run, storage_on, verbs, where_of
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage import ResolvedPair
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from vfs.results import Result
    from vfs.storage.backends.database import DatabaseStorage


async def show(storage: DatabaseStorage, label: str, call: Callable[[], Awaitable[Result]]) -> None:
    with recorded(storage) as statements:
        result = await call()
    outcome = "ok" if result.success else f"refused {[str(e.kind) for e in result.errors]}"
    print(f"-- {label}: {len(statements)} statements, {outcome}")
    print(f"   verbs: {' '.join(verbs(statements))}")
    updates = [s for s in statements if s.upper().startswith("UPDATE") and "vfs_entries" in s.split(" SET ")[0]]
    for statement in updates[:1]:
        print(f"   first UPDATE of vfs_entries: {where_of(statement)}")
        if " FROM (VALUES" in statement:
            print("   shape: a VALUES join")


async def one_engine(storage: DatabaseStorage) -> None:
    p = Path
    await storage.mkdir(path=p("/d"))
    await storage.write(entries=[Entry(path=p("/d/f"), content="one")])
    await storage.write(entries=[Entry(path=p("/d/g"), content="one")])
    await storage.write(entries=[Entry(path=p("/d/h"), content="one")])
    await storage.mkdir(path=p("/d/sub"))
    await storage.write(entries=[Entry(path=p("/d/sub/x"), content="one")])
    await storage.mkdir(path=p("/empty"))
    # Warm the host: the first call of a storage reads its meta row.
    await storage.stat(path=p("/d/f"))

    await show(storage, "write, an update", lambda: storage.write(entries=[Entry(path=p("/d/f"), content="two")]))
    await show(
        storage,
        "write, an update with the right expected version",
        lambda: storage.write(entries=[Entry(path=p("/d/f"), content="three")], if_versions={p("/d/f"): 2}),
    )
    await show(
        storage,
        "write, a stale expected version",
        lambda: storage.write(entries=[Entry(path=p("/d/f"), content="four")], if_versions={p("/d/f"): 1}),
    )
    await show(storage, "edit", lambda: storage.edit(edits=[EditOperation(old="one", new="uno")], path=p("/d/g")))
    await show(storage, "delete of a file", lambda: storage.delete(path=p("/d/h")))
    await show(storage, "restore of a file", lambda: storage.restore(path=p("/d/h")))
    await show(storage, "delete of a directory, cascading", lambda: storage.delete(path=p("/d/sub")))
    await show(
        storage, "delete of an empty directory, no cascade", lambda: storage.delete(path=p("/empty"), cascade=False)
    )
    await show(
        storage,
        "move of a file within one directory",
        lambda: storage.move(operations=[ResolvedPair(p("/d/f"), p("/d/f2"))]),
    )


async def main() -> None:
    for engine in engines():
        print(f"== {engine}")
        async with storage_on(engine) as (storage, _):
            await one_engine(storage)


if __name__ == "__main__":
    run(main)
