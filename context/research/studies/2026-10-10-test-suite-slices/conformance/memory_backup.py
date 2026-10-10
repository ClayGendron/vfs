"""Restore a template schema into InMemoryStorage's StaticPool connection before first touch; time each phase."""
import asyncio, sqlite3, time, statistics
from vfs.storage.backends.memory import InMemoryStorage
from vfs.models import Entry
from vfs.paths import Path

async def make_template():
    s = InMemoryStorage()
    await s._host.ensure_ready()
    tpl = sqlite3.connect(":memory:", check_same_thread=False)
    async with s._host.engine.connect() as conn:
        raw = await conn.get_raw_connection()
        await raw.driver_connection.backup(tpl)
    ident = s._host.mount_identity
    await s.close()
    return tpl, ident

async def restore(s, tpl):
    async with s._host.engine.connect() as conn:
        raw = await conn.get_raw_connection()
        aio = raw.driver_connection
        await aio._execute(tpl.backup, aio._conn)

async def main():
    tpl, ident = await make_template()
    for label in ("plain", "template", "plain", "template"):
        acc = {k: [] for k in ("construct", "restore", "first_touch", "write", "close")}
        idents = set()
        for _ in range(15):
            def tick(k, w0, c0): acc[k].append((time.perf_counter()-w0, time.process_time()-c0))
            w0=time.perf_counter(); c0=time.process_time(); s = InMemoryStorage(); tick("construct", w0, c0)
            w0=time.perf_counter(); c0=time.process_time()
            if label == "template": await restore(s, tpl)
            tick("restore", w0, c0)
            w0=time.perf_counter(); c0=time.process_time(); r = await s._host.ensure_ready(); assert r is None, r; tick("first_touch", w0, c0)
            idents.add(s._host.mount_identity)
            w0=time.perf_counter(); c0=time.process_time()
            r = await s.write(entries=[Entry(path=Path("/a/b.txt"), content="hi")], parents=True); assert r.success, r
            tick("write", w0, c0)
            w0=time.perf_counter(); c0=time.process_time(); await s.close(); tick("close", w0, c0)
        print(label, "identity shared with template:", idents == {ident})
        for k, v in acc.items():
            print(f"  {k:12s} wall {statistics.median(x[0] for x in v)*1000:6.1f}ms cpu {statistics.median(x[1] for x in v)*1000:6.1f}ms")
asyncio.run(main())
