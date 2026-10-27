"""Crash at each mutating statement of one write batch; check the store is all-old or all-new."""
import asyncio, sqlite3, sys, tempfile, pathlib
from sqlalchemy import event, select, func, text
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

MUT = ("INSERT", "UPDATE", "DELETE")

async def seed(url):
    s = DatabaseStorage(url=url)
    r = await s.write(entries=[Entry(path=Path("/d/a.txt"), content="old a")], parents=True)
    assert r.success, r
    return s

BATCH = lambda: [
    Entry(path=Path("/d/a.txt"), content="new a"),
    Entry(path=Path("/d/b.txt"), content="new b"),
    Entry(path=Path("/e/c.txt"), content="new c"),
]

async def snapshot(s):
    t = s._host.tables
    out = {}
    async with s._host.engine.connect() as c:
        for name in ("entry", "content", "versions", "edges", "segments"):
            tab = getattr(t, name)
            out[name] = (await c.execute(select(func.count()).select_from(tab))).scalar()
        rows = (await c.execute(select(t.entry.c.path, t.entry.c.version, t.entry.c.content_hash).order_by(t.entry.c.path))).all()
        out["entries"] = [tuple(r) for r in rows]
        body = (await c.execute(select(t.content.c.content).order_by(t.content.c.content))).scalars().all()
        out["bodies"] = list(body)
    return out

async def run(k, tmp):
    url = f"sqlite+aiosqlite:///{tmp}/k{k}.sqlite"
    s = await seed(url)
    before = await snapshot(s)
    n = {"i": 0, "fired": False, "stmts": []}
    def hook(conn, cursor, statement, params, context, many):
        verb = statement.lstrip().split(None, 1)[0].upper()
        if verb in MUT:
            n["i"] += 1
            n["stmts"].append(statement.split("(")[0][:60].replace("\n", " "))
            if n["i"] == k and not n["fired"]:
                n["fired"] = True
                raise sqlite3.OperationalError("disk I/O error (injected)")
    event.listen(s._host.engine.sync_engine, "before_cursor_execute", hook)
    try:
        r = await s.write(entries=BATCH(), parents=True)
    except sqlite3.OperationalError as exc:
        r = exc
    event.remove(s._host.engine.sync_engine, "before_cursor_execute", hook)
    await s.close()
    s2 = DatabaseStorage(url=url)  # the "reboot": a fresh process view of the same file
    await s2.stat(path=Path("/d"))
    after = await snapshot(s2)
    await s2.close()
    return r, before, after, n

async def main():
    tmp = tempfile.mkdtemp()
    # reference: no fault
    r, before, ref, n = await run(10**9, tmp)
    assert r.success
    total = n["i"]
    print(f"mutating statements in the batch: {total}")
    for i, st in enumerate(n["stmts"], 1):
        print(f"  {i:2d} {st}")
    verdicts = {"all-old": 0, "all-new": 0, "TORN": 0}
    for k in range(1, total + 1):
        r, before, after, n = await run(k, tmp)
        state = "all-old" if after == before else "all-new" if after == ref else "TORN"
        verdicts[state] += 1
        outcome = "raised" if isinstance(r, Exception) else f"success={r.success}"
        print(f"crash at stmt {k:2d}: {outcome} store={state}")
    print(verdicts)

asyncio.run(main())
