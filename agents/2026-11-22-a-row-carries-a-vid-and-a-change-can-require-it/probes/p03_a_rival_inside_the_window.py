"""What a rival's commit inside the window does to a guarded write, edit, delete, move and restore, on each engine.

The etag spec (decision 9) says a rival that commits between a verb's
snapshot and its guarded statement ends in a refusal on every engine: by
a serialization failure and a second run on Postgres for ``write`` and
``edit``, by a claim that matches no row and a second run for ``delete``
and ``move``, and never at all on SQLite, where the writer lock is held.

``if_match`` is not built, so the probe drives today's verbs through the
seams the code declares. A ``write`` states ``if_versions``, the guard an
etag will ride on. ``edit``, ``delete``, ``move`` and ``restore`` state
nothing today, so the probe shows what their guard does: the engine
errors the victim's connection raised, how many times the victim read
its snapshot, and the version the result reports, which is the rival's
state when the verb ran again. The rival is a second storage object on
the same database, so its commit is a real second transaction.

On SQLite the rival is expected not to commit: it is given 8 seconds and
its outcome is printed. A rival that never ran leaves the victim's
answer as if no rival existed.

    VFS_TEST_POSTGRES_URL=postgresql+asyncpg://vfs:vfs@localhost:54320/vfs \
        uv run python agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/probes/p03_a_rival_inside_the_window.py
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from sqlalchemy import event, select

from harness import engines, recorded, run, storage_on
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import seams
from vfs.storage.replace import EditOperation

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from vfs.results import Result
    from vfs.storage.backends.database import DatabaseStorage

RIVAL_SECONDS = 8.0
P = Path


async def staged(
    engine: str,
    label: str,
    seam_name: str,
    seed: Callable[[DatabaseStorage], Awaitable[None]],
    rival_call: Callable[[DatabaseStorage], Awaitable[Result]],
    victim_call: Callable[[DatabaseStorage], Awaitable[Result]],
    after: str,
) -> None:
    async with storage_on(engine) as (storage, make_rival):
        await seed(storage)
        rival_storage = make_rival()
        await rival_storage.stat(path=P("/"))
        rival_outcome: list[str] = []
        engine_errors: list[str] = []

        async def handler() -> None:
            seams.clear(seam_name)
            try:
                async with asyncio.timeout(RIVAL_SECONDS):
                    result = await rival_call(rival_storage)
                rival_outcome.append("committed" if result.success else f"refused {[str(e.kind) for e in result.errors]}")
            except TimeoutError:
                rival_outcome.append(f"did not finish in {RIVAL_SECONDS:.0f} s (blocked)")

        def on_error(context: Any) -> None:
            origin = context.original_exception
            code = getattr(origin, "sqlstate", None) or getattr(origin, "sqlite_errorname", None)
            engine_errors.append(f"{code}: {str(origin).splitlines()[0][:70]}")

        sync_engine = storage._host.engine.sync_engine
        event.listen(sync_engine, "handle_error", on_error)
        try:
            with recorded(storage) as statements, seams.installed(seam_name, handler):
                victim = await victim_call(storage)
        finally:
            event.remove(sync_engine, "handle_error", on_error)
        updates = sum(1 for s in statements if s.upper().startswith("UPDATE"))
        answer = (
            f"ok {[(o.status, o.version) for o in victim.observations]}"
            if victim.success
            else f"refused {[(str(e.kind), e.data, e.retryable) for e in victim.errors]}"
        )
        entry = storage._host.tables.entry
        async with storage._host.session_factory() as session:
            row = (
                await session.execute(
                    select(entry.c.path, entry.c.version, entry.c.deleted_at).where(entry.c.path == after)
                )
            ).one_or_none()
        state = "no row" if row is None else f"v={row.version} {'live' if row.deleted_at is None else 'tombstone'}"
        print(f"-- {label}")
        print(f"   rival: {rival_outcome[0] if rival_outcome else 'the seam never fired'}")
        print(f"   victim: {answer}")
        print(f"   victim's engine errors: {engine_errors or 'none'}; statements {len(statements)}, of them UPDATE {updates}")
        print(f"   {after} afterwards: {state}")


async def seed_file(storage: DatabaseStorage) -> None:
    await storage.mkdir(path=P("/d"))
    await storage.write(entries=[Entry(path=P("/d/a.txt"), content="one")])


async def seed_deleted(storage: DatabaseStorage) -> None:
    await seed_file(storage)
    await storage.delete(path=P("/d/a.txt"))


async def one_engine(engine: str) -> None:
    target = P("/d/a.txt")

    def write(body: str, **more: Any) -> Callable[[DatabaseStorage], Awaitable[Result]]:
        return lambda s: s.write(entries=[Entry(path=target, content=body)], **more)

    def move_away(s: DatabaseStorage) -> Awaitable[Result]:
        return s.move(operations=[ResolvedPair(target, P("/d/moved.txt"))])

    await staged(
        engine, "write(if_versions) against a rival write of another body", "write:before-apply",
        seed_file, write("rival"), write("mine", if_versions={target: 1}), "/d/a.txt",
    )  # fmt: skip
    await staged(
        engine, "write(if_versions) against a rival write of the same body", "write:before-apply",
        seed_file, write("same"), write("same", if_versions={target: 1}), "/d/a.txt",
    )  # fmt: skip
    await staged(
        engine, "write(if_versions) against a rival that moved the row away", "write:before-apply",
        seed_file, move_away, write("mine", if_versions={target: 1}), "/d/moved.txt",
    )  # fmt: skip
    await staged(
        engine, "write(if_versions) against a rival that deleted the row", "write:before-apply",
        seed_file, lambda s: s.delete(path=target), write("mine", if_versions={target: 1}), "/d/a.txt",
    )  # fmt: skip
    await staged(
        engine, "a plain write against a rival write of another body", "write:before-apply",
        seed_file, write("rival"), write("mine"), "/d/a.txt",
    )  # fmt: skip
    await staged(
        engine, "edit against a rival write that keeps the text the edit matches", "write:before-apply",
        seed_file, write("one and more"), lambda s: s.edit(edits=[EditOperation(old="one", new="uno")], path=target),
        "/d/a.txt",
    )  # fmt: skip
    await staged(
        engine, "delete against a rival write to the target", "delete:post-collect",
        seed_file, write("rival"), lambda s: s.delete(path=target), "/d/a.txt",
    )  # fmt: skip
    await staged(
        engine, "delete of a directory against a rival child made in it", "delete:post-collect",
        seed_file, lambda s: s.write(entries=[Entry(path=P("/d/new.txt"), content="x")]),
        lambda s: s.delete(path=P("/d")), "/d",
    )  # fmt: skip
    await staged(
        engine, "move against a rival write to the source", "transfer:post-collect",
        seed_file, write("rival"), move_away, "/d/moved.txt",
    )  # fmt: skip
    await staged(
        engine, "restore against a rival write that revives the row", "restore:post-resolve",
        seed_deleted, write("rival"), lambda s: s.restore(path=target), "/d/a.txt",
    )  # fmt: skip


async def main() -> None:
    for engine in engines():
        print(f"== {engine}")
        await one_engine(engine)


if __name__ == "__main__":
    run(main, deadline=420.0)
