"""Spec 179 probe: one bad row in each plural mutating verb's batch; every table compared. Counts only."""
import asyncio, tempfile
from sqlalchemy import event, select
from vfs.authority import Authority, Principal
from vfs.models import Edge, Entry, Observation
from vfs.paths import Path
from vfs.storage import ResolvedPair
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.replace import EditOperation

async def image(s):
    t = s._host.tables; out = {}
    async with s._host.engine.connect() as c:
        for name in t._fields:
            if name == "metadata": continue
            out[name] = sorted(tuple(repr(v) for v in r) for r in (await c.execute(select(getattr(t, name)))).all())
    return out

async def seed(s):
    await s.write(entries=[Entry(path=Path("/d/a.txt"), content="a"), Entry(path=Path("/d/b.txt"), content="b"), Entry(path=Path("/d/bin.dat"), data=b"\x00\x01")], parents=True)
    await s.mkdir(path=Path("/dir"))
    await s.mkedge(edges=[Edge(source=Path("/d/a.txt"), target=Path("/d/b.txt"), edge_type="refs")])
    await s.grant(path=Path("/"), principal="alice", level="read_write")

P = Path
CASES = {
  "write: bad = file under a file (parents=True)": lambda s: s.write(entries=[Entry(path=P("/d/a.txt"), content="A"), Entry(path=P("/n/new.txt"), content="n"), Entry(path=P("/d/blob2"), data=b"\x02"), Entry(path=P("/d/b.txt/z.txt"), content="z")], parents=True),
  "write: bad = occupied, overwrite=False": lambda s: s.write(entries=[Entry(path=P("/d/c.txt"), content="c"), Entry(path=P("/d/a.txt"), content="A")], overwrite=False),
  "write: bad = onto a directory": lambda s: s.write(entries=[Entry(path=P("/d/a.txt"), content="A"), Entry(path=P("/dir"), content="x")]),
  "write as alice: bad = file under a file": lambda s: s.write(entries=[Entry(path=P("/d/a.txt"), content="A2"), Entry(path=P("/d/b.txt/z.txt"), content="z")], authority=Authority.of(Principal("alice"))),
  "edit: bad = failed match": lambda s: s.edit(observations=[Observation(path=P("/d/a.txt")), Observation(path=P("/d/b.txt"))], edits=[EditOperation(old="a", new="A")]),
  "delete: bad = missing": lambda s: s.delete(observations=[Observation(path=P("/d/a.txt")), Observation(path=P("/nope.txt"))]),
  "move: bad = missing source": lambda s: s.move(operations=[ResolvedPair(P("/d/a.txt"), P("/d/a2.txt")), ResolvedPair(P("/nope"), P("/n2"))]),
  "copy: bad = occupied dest": lambda s: s.copy(operations=[ResolvedPair(P("/d/a.txt"), P("/d/a3.txt")), ResolvedPair(P("/d/a.txt"), P("/d/b.txt"))]),
  "mkedge: bad = missing endpoint": lambda s: s.mkedge(edges=[Edge(source=P("/d/b.txt"), target=P("/d/a.txt"), edge_type="refs"), Edge(source=P("/d/a.txt"), target=P("/nope"), edge_type="refs")]),
  "rmedge: bad = missing source": lambda s: s.rmedge(edges=[Edge(source=P("/d/a.txt"), target=P("/d/b.txt"), edge_type="refs"), Edge(source=P("/nope"), target=P("/d/b.txt"), edge_type="refs")]),
  "restore: bad = live row": lambda s: s.restore(observations=[Observation(path=P("/d/b.txt"))]),
}

async def main():
    tmp = tempfile.mkdtemp()
    for i, (name, fn) in enumerate(CASES.items()):
        s = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/{i}.sqlite"); await s.first_touch(); await seed(s)
        commits = {"n": 0}
        event.listen(s._host.engine.sync_engine, "commit", lambda conn: commits.__setitem__("n", commits["n"] + 1))
        before = await image(s)
        r = await fn(s)
        after = await image(s)
        diff = sorted(t for t in before if before[t] != after[t])
        print(f"{name:<48} success={r.success} errors={sorted(str(e.kind) for e in r.errors if e.severity=='error')} warnings={sum(1 for e in r.errors if e.severity!='error')} commits={commits['n']} tables_changed={diff}")
        await s.close()
asyncio.run(main())
