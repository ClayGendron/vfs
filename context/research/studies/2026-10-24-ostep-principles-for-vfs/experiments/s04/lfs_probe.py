"""Study 04 probe: version growth, sweep reach, tombstones in a listing, sibling locality.

Counts rows and statements; never times. SQLite in-process (InMemoryStorage).
"""

from __future__ import annotations

import asyncio
from collections import Counter

from sqlalchemy import event, text

from vfs.authority import Authority
from vfs.base import VirtualFileSystem
from vfs.models import Entry, Observation
from vfs.storage.backends.memory import InMemoryStorage

N = 1_000


async def count(storage, sql: str) -> int:
    async with storage._host.engine.connect() as conn:
        return int((await conn.execute(text(sql))).scalar_one())


async def rows(storage, sql: str):
    async with storage._host.engine.connect() as conn:
        return (await conn.execute(text(sql))).all()


async def main() -> None:
    storage = InMemoryStorage(trash_days=0)
    fs = VirtualFileSystem(storage=storage)
    sysa = Authority.system()
    await storage.first_touch()
    stmts: list[str] = []

    @event.listens_for(storage._host.engine.sync_engine, "before_cursor_execute")
    def rec(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        stmts.append(statement)

    def heads() -> str:
        return ", ".join(f"{k}={v}" for k, v in sorted(Counter(s.split(None, 1)[0] for s in stmts).items()))

    out: list[str] = []
    # 1. ETL rewrite: N files written, then overwritten three times with new bodies.
    for gen in range(4):
        stmts.clear()
        r = await fs.write([Entry(path=f"/etl/f{i:04}.txt", content=f"gen {gen} row {i}\n" * 20) for i in range(N)],
                           parents=True, overwrite=True, authority=sysa)
        v = await count(storage, "select count(*) from vfs_versions")
        vb = await count(storage, "select coalesce(sum(length(content)),0) from vfs_versions")
        cb = await count(storage, "select coalesce(sum(length(content)),0) from vfs_content")
        out.append(f"etl gen {gen}: ok={r.success} statements={len(stmts)} versions={v} version_bytes={vb} live_bytes={cb}")
    # Identical rewrite mints nothing.
    await fs.write([Entry(path=f"/etl/f{i:04}.txt", content=f"gen 3 row {i}\n" * 20) for i in range(N)],
                   overwrite=True, authority=sysa)
    out.append(f"identical rewrite: versions={await count(storage, 'select count(*) from vfs_versions')}")
    # Sweep at the trash head with retention 0: no tombstones, so live history is untouched.
    stmts.clear()
    s = await fs.sweep(authority=sysa)
    n, h = len(stmts), heads()
    out.append(f"sweep(trash, days=0) with no tombstones: ok={s.success} observed={len(s.observations)} "
               f"versions_after={await count(storage, 'select count(*) from vfs_versions')} statements={n} [{h}]")

    # 2. Tombstones inside a listing: 1000 children, delete 900, ls the parent.
    await fs.write([Entry(path=f"/d/c{i:04}.txt", content=f"{i}\n") for i in range(N)], parents=True, authority=sysa)
    stmts.clear()
    d = await fs.delete(observations=[Observation(path=f"/d/c{i:04}.txt", kind="file") for i in range(900)], authority=sysa)
    out.append(f"delete 900 children: ok={d.success} statements={len(stmts)} [{heads()}]")
    pid = (await rows(storage, "select entry_id from vfs_entries where path='/d'"))[0][0]
    stmts.clear()
    ls = await fs.ls("/d", authority=sysa)
    ls_stmts = list(stmts)
    in_range = await count(storage, f"select count(*) from vfs_entries where parent_id = x'{pid.hex()}'")
    out.append(f"ls(/d) after delete: rows={len(ls.observations)} statements={len(ls_stmts)} "
               f"rows_in_(parent_id,name)_range={in_range}")
    sel = [s for s in ls_stmts if "parent_id IN" in s or "parent_id =" in s]
    if sel:
        out.append("  children select: " + " ".join(sel[-1].split())[:400])
        plan = await rows(storage, "explain query plan " + sel[-1].replace("?", "NULL"))
        out.append("  plan of children select: " + " | ".join(str(p[-1]) for p in plan))
    stmts.clear()
    s = await fs.sweep(authority=sysa)
    n, h = len(stmts), heads()
    in_range2 = await count(storage, f"select count(*) from vfs_entries where parent_id = x'{pid.hex()}'")
    out.append(f"sweep(trash, days=0) after delete: observed={len(s.observations)} statements={n} [{h}] "
               f"rows_in_range_after={in_range2}")
    vers = await count(storage, "select count(*) from vfs_versions")
    out.append(f"versions still held (live /etl history): {vers}")

    # 3. Sibling locality: alternate single-file writes between two directories.
    for i in range(8):
        await fs.write([Entry(path=f"/{'ab'[i % 2]}/x{i}.txt", content="x\n")], parents=True, authority=sysa)
    a = await rows(storage, "select id, path from vfs_entries where path like '/a/%' order by name")
    b = await rows(storage, "select id, path from vfs_entries where path like '/b/%' order by name")
    out.append(f"surrogate ids of /a children: {[r[0] for r in a]}; of /b children: {[r[0] for r in b]}")
    idx = await rows(storage, "select name from pragma_index_list('vfs_entries')")
    out.append(f"entries indexes: {sorted(r[0] for r in idx)}")
    await fs.close()
    print("\n".join(out))


asyncio.run(main())
