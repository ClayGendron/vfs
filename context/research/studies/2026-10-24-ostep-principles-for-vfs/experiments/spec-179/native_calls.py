"""Spec 179 probe: native calls per verb, on the loop thread vs elsewhere. Counts only."""
import asyncio, tempfile, threading
from collections import Counter
from vfs import _native
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
from vfs.storage.backends.database import offload as offload_mod
from vfs.storage.backends.database import backend as backend_mod

LOOP = {"ident": None}
CALLS: Counter = Counter()

def wrap_fn(name, fn):
    def w(*a, **k):
        where = "loop" if threading.get_ident() == LOOP["ident"] else "worker"
        CALLS[(name, where)] += 1
        return fn(*a, **k)
    return w

class Proxy:
    def __init__(self, cls_name, inner):
        object.__setattr__(self, "_n", cls_name); object.__setattr__(self, "_i", inner)
    def __getattr__(self, attr):
        v = getattr(self._i, attr)
        return wrap_fn(f"{self._n}.{attr}", v) if callable(v) else v

def wrap_cls(name, cls):
    def make(*a, **k):
        where = "loop" if threading.get_ident() == LOOP["ident"] else "worker"
        CALLS[(f"{name}()", where)] += 1
        return Proxy(name, cls(*a, **k))
    return make

for name in dir(_native):
    if name.startswith("_"): continue
    v = getattr(_native, name)
    if isinstance(v, type):
        setattr(_native, name, wrap_cls(name, v))
    elif callable(v):
        setattr(_native, name, wrap_fn(name, v))

HOPS = Counter()
orig = offload_mod.call_offloaded
async def counted(executor, work):
    HOPS["hop"] += 1
    return await orig(executor, work)
offload_mod.call_offloaded = counted
backend_mod.call_offloaded = counted
import vfs.storage.backends.database.grep as g, vfs.storage.backends.database.glean as gl, vfs.storage.backends.database.indexing as ix, vfs.storage.backends.database.lexical as lx, vfs.storage.backends.database.signals as sg
for m in (g, gl, ix, lx, sg):
    if hasattr(m, "call_offloaded"): m.call_offloaded = counted

async def trace(title, coro):
    CALLS.clear(); HOPS.clear()
    r = await coro
    print(f"{title:<28} ok={r.success} hops={HOPS['hop']} calls={dict(sorted(CALLS.items()))}")

async def main():
    LOOP["ident"] = threading.get_ident()
    tmp = tempfile.mkdtemp()
    s = DatabaseStorage(url=f"sqlite+aiosqlite:///{tmp}/a.sqlite")
    await s.first_touch()
    await trace("write 50 files", s.write(entries=[Entry(path=Path(f"/d/f{i}.md"), content=f"alpha beta gamma {i}\n" * 20) for i in range(50)], parents=True))
    await trace("read", s.read(path=Path("/d/f1.md")))
    await trace("grep before reindex", s.grep(pattern="gamma 1"))
    await trace("reindex", s.reindex())
    await trace("grep indexed", s.grep(pattern="gamma 1"))
    await trace("glob", s.glob(patterns=("/d/*.md",)))
    await trace("glean", s.glean(query="alpha gamma"))
    await s.close()
asyncio.run(main())
