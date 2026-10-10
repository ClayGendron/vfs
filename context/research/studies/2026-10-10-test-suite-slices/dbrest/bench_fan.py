import asyncio, time, tempfile
from sqlalchemy import event
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
async def fan(n):
    s=DatabaseStorage(url=f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/vfs.sqlite")
    assert (await s.write(entries=[Entry(path=Path("/part00000/a.parquet"), content="x")], parents=True)).success
    stmts=[]
    @event.listens_for(s._host.engine.sync_engine, "before_cursor_execute")
    def rec(conn, cursor, statement, parameters, context, executemany): stmts.append(statement)
    t=time.perf_counter(); r=await s.glob(patterns=tuple(f"/part{i:05}/**/*.parquet" for i in range(n))); e=time.perf_counter()-t
    assert [str(o.path) for o in r.observations]==["/part00000/a.parquet"]
    await s.close(); return e, sum(1 for x in stmts if "LIKE" in x and x.startswith("SELECT"))
async def main():
    await fan(400)
    for n in (10_000, 2_000, 1_000, 400): e,f=await fan(n); print(f"glob fan N={n:6}: {e:5.2f}s  fan statements={f}")
asyncio.run(main())
