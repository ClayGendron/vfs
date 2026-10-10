import asyncio, time, tempfile, pathlib, sys
from vfs.models import Entry, Edge
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage

async def one(url, n_writes=1):
    t0 = time.perf_counter()
    s = DatabaseStorage(url=url)
    r = await s.write(entries=[Entry(path=Path("/a.txt"), content="x")], parents=True)
    assert r.success
    t1 = time.perf_counter()
    for i in range(n_writes):
        r = await s.write(entries=[Entry(path=Path(f"/b{i}.txt"), content="y")], parents=True)
    t2 = time.perf_counter()
    await s.close()
    t3 = time.perf_counter()
    return t1-t0, (t2-t1)/max(n_writes,1), t3-t2

async def tenk(url, kind):
    s = DatabaseStorage(url=url)
    t0 = time.perf_counter()
    if kind == "entry":
        entries = [Entry(path=Path(f"/lake/d{i // 500:02}/r{i:05}.json"), content=f'{{"row": {i}}}') for i in range(10_000)]
        w = await s.write(entries=entries, parents=True); assert w.success
        t1 = time.perf_counter()
        created = [o for o in w.observations if str(o.path).endswith(".json")]
        st = await s.stat(observations=created); assert st.success and len(st.observations)==10_000
        t2 = time.perf_counter()
        out = {"write": t1-t0, "stat": t2-t1}
    else:
        entries = [Entry(path=Path("/hub.py"), content="hub")] + [Entry(path=Path(f"/spokes/s{i:05}.py"), content=f"s{i}") for i in range(10_000)]
        assert (await s.write(entries=entries, parents=True)).success
        t1 = time.perf_counter()
        edges = [Edge(source=Path("/hub.py"), target=Path(f"/spokes/s{i:05}.py"), edge_type="imports") for i in range(10_000)]
        c = await s.mkedge(edges=edges); assert c.success
        t2 = time.perf_counter()
        u = await s.mkedge(edges=edges); assert u.success
        t3 = time.perf_counter()
        d = await s.rmedge(edges=edges); assert d.success
        t4 = time.perf_counter()
        out = {"write": t1-t0, "mkedge": t2-t1, "mkedge2": t3-t2, "rmedge": t4-t3}
    await s.close()
    return out

async def main():
    for label, mk in (("file", lambda: f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/vfs.sqlite"), ("memory", lambda: "sqlite+aiosqlite:///:memory:")):
        await one(mk())  # warm
        res = [await one(mk(), 10) for _ in range(5)]
        o = sum(r[0] for r in res)/5; w = sum(r[1] for r in res)/5; c = sum(r[2] for r in res)/5
        print(f"{label:6} open+first write {o*1000:6.1f} ms | extra 1-file write {w*1000:6.1f} ms | close {c*1000:5.1f} ms")
    for kind in ("entry", "edge"):
        for label, mk in (("file", lambda: f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/vfs.sqlite"), ("memory", lambda: "sqlite+aiosqlite:///:memory:")):
            t0=time.perf_counter(); out = await tenk(mk(), kind); tot=time.perf_counter()-t0
            print(f"10k {kind:5} {label:6} total {tot:5.2f}s  " + "  ".join(f"{k} {v:.2f}" for k,v in out.items()))

asyncio.run(main())
