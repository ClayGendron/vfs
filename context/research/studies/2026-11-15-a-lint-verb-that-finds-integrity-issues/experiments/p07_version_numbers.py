"""Probe 07: which verbs raise an entry's version, and which of them leave a version row."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from lint_common import SYSTEM, fetch, make


async def state(storage, label: str) -> None:
    t = storage._host.tables
    found = await fetch(
        storage,
        select(t.entry.c.path, t.entry.c.version, t.entry.c.entry_id).where(t.entry.c.kind == "file").order_by(t.entry.c.path),
    )
    for row in found:
        numbers = [r[0] for r in await fetch(storage, select(t.versions.c.version_number).where(t.versions.c.entry_id == row.entry_id).order_by(t.versions.c.version_number))]
        print(f"    {label}: {row.path} entry.version={row.version} version rows={numbers}")


async def main() -> None:
    fs, storage = make()
    await fs.write(path="/d/a.txt", content="one\n", parents=True, authority=SYSTEM)
    await state(storage, "after create")
    await fs.write(path="/d/a.txt", content="two\n", authority=SYSTEM)
    await state(storage, "after overwrite")
    await fs.write(path="/d/a.txt", content="two\n", authority=SYSTEM)
    await state(storage, "after an identical overwrite")
    await fs.edit("/d/a.txt", "two", "three", authority=SYSTEM)
    await state(storage, "after edit")
    await fs.move("/d/a.txt", "/d/b.txt", authority=SYSTEM)
    await state(storage, "after move")
    await fs.delete("/d/b.txt", authority=SYSTEM)
    await fs.restore("/d/b.txt", authority=SYSTEM)
    await state(storage, "after delete and restore")
    await fs.copy("/d/b.txt", "/d/c.txt", authority=SYSTEM)
    await state(storage, "after copy")
    await fs.close()


asyncio.run(main())
