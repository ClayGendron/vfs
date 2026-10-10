"""Unprofiled: create_all checkfirst True vs False, build_vfs_tables, file copy, DELETE-all reset."""
import asyncio, time, tempfile, shutil, os, statistics
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from vfs.models.rows import build_vfs_tables

def med(f, n=15):
    xs=[]
    for _ in range(n):
        c0=time.process_time(); w0=time.perf_counter(); f(); xs.append((time.perf_counter()-w0, time.process_time()-c0))
    return "wall %.1fms cpu %.1fms" % (statistics.median(x[0] for x in xs)*1000, statistics.median(x[1] for x in xs)*1000)

print("build_vfs_tables:", med(lambda: build_vfs_tables(schema=None, native_embedding=None)))

async def create(url, checkfirst):
    t = build_vfs_tables(schema=None, native_embedding=None)
    eng = create_async_engine(url)
    async with eng.begin() as conn:
        await conn.run_sync(t.metadata.create_all, checkfirst=checkfirst)
    await eng.dispose()

async def amed(coro_factory, n=15):
    xs=[]
    for _ in range(n):
        c0=time.process_time(); w0=time.perf_counter(); await coro_factory(); xs.append((time.perf_counter()-w0, time.process_time()-c0))
    return "wall %.1fms cpu %.1fms" % (statistics.median(x[0] for x in xs)*1000, statistics.median(x[1] for x in xs)*1000)

async def main():
    tmp = tempfile.mkdtemp()
    await create("sqlite+aiosqlite://", True)  # warm
    print("memory create_all checkfirst=True :", await amed(lambda: create("sqlite+aiosqlite://", True)))
    print("memory create_all checkfirst=False:", await amed(lambda: create("sqlite+aiosqlite://", False)))
    i=[0]
    def nxt():
        i[0]+=1; return f"sqlite+aiosqlite:///{tmp}/f{i[0]}.sqlite"
    print("file   create_all checkfirst=True :", await amed(lambda: create(nxt(), True)))
    print("file   create_all checkfirst=False:", await amed(lambda: create(nxt(), False)))
    # existing schema: create_all(checkfirst=True) with nothing to do
    await create(f"sqlite+aiosqlite:///{tmp}/tpl.sqlite", True)
    print("file   create_all on existing schema (checkfirst=True, no-op):", await amed(lambda: create(f"sqlite+aiosqlite:///{tmp}/tpl.sqlite", True)))
    print("template size bytes", os.path.getsize(f"{tmp}/tpl.sqlite"))
    print("shutil.copy template:", med(lambda: shutil.copy(f"{tmp}/tpl.sqlite", f"{tmp}/copy.sqlite")))
    # sync sqlite3 executescript of the same DDL, for reference
    from sqlalchemy import create_engine
    from sqlalchemy.schema import CreateTable, CreateIndex
    t = build_vfs_tables(schema=None, native_embedding=None)
    eng = create_engine("sqlite://")
    ddl = []
    for tb in t.metadata.sorted_tables:
        ddl.append(str(CreateTable(tb).compile(eng)))
        for ix in tb.indexes: ddl.append(str(CreateIndex(ix).compile(eng)))
    script = ";\n".join(ddl)
    import sqlite3
    def es():
        c = sqlite3.connect(":memory:"); c.executescript(script); c.close()
    print("sqlite3 executescript same DDL (memory):", med(es), "statements", len(ddl))
    # DELETE-all reset
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(t.metadata.create_all)
    async def reset():
        async with eng.begin() as conn:
            for tb in reversed(t.metadata.sorted_tables):
                await conn.execute(tb.delete())
    print("DELETE-all reset of 21 empty tables:", await amed(reset))
    await eng.dispose()
asyncio.run(main())
