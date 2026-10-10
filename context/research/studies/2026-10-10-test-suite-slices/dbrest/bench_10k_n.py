import asyncio, time, tempfile
from sqlalchemy import event
from vfs.models import Entry, Edge
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
async def entry(n):
    s = DatabaseStorage(url=f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/vfs.sqlite")
    await s.stat(path=Path("/"))
    stmts=[]
    @event.listens_for(s._host.engine.sync_engine, "before_cursor_execute")
    def rec(conn, cursor, statement, parameters, context, executemany): stmts.append(statement)
    t=time.perf_counter()
    entries=[Entry(path=Path(f"/lake/d{i // 500:02}/r{i:05}.json"), content=f'{{"row": {i}}}') for i in range(n)]
    w=await s.write(entries=entries, parents=True); assert w.success
    created=[o for o in w.observations if str(o.path).endswith(".json")]; assert len(created)==n
    st=await s.stat(observations=created); assert st.success and len(st.observations)==n
    e=time.perf_counter()-t; await s.close()
    ins=sum(1 for x in stmts if x.startswith("INSERT")); sel=sum(1 for x in stmts if x.startswith("SELECT"))
    return e, ins, sel, len(stmts)
async def edge(n):
    s = DatabaseStorage(url=f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/vfs.sqlite")
    await s.stat(path=Path("/"))
    t=time.perf_counter()
    entries=[Entry(path=Path("/hub.py"), content="hub")]+[Entry(path=Path(f"/spokes/s{i:05}.py"), content=f"s{i}") for i in range(n)]
    assert (await s.write(entries=entries, parents=True)).success
    edges=[Edge(source=Path("/hub.py"), target=Path(f"/spokes/s{i:05}.py"), edge_type="imports") for i in range(n)]
    stmts=[]
    @event.listens_for(s._host.engine.sync_engine, "before_cursor_execute")
    def rec(conn, cursor, statement, parameters, context, executemany): stmts.append(statement)
    c=await s.mkedge(edges=edges); assert c.success and len(c.observations)==n
    u=await s.mkedge(edges=edges); assert u.success
    d=await s.rmedge(edges=edges); assert d.success
    e=time.perf_counter()-t; await s.close()
    return e, len(stmts)
async def main():
    await entry(200)
    for n in (10_000, 5_000, 2_500, 1_000):
        e,ins,sel,tot=await entry(n); print(f"entry N={n:6}: {e:5.2f}s  INSERT stmts={ins:3} SELECT stmts={sel:3} all={tot}")
    for n in (10_000, 2_500, 1_000):
        e,tot=await edge(n); print(f"edge  N={n:6}: {e:5.2f}s  stmts during mkedge/mkedge/rmedge={tot}")
asyncio.run(main())
