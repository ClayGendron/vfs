"""f15-p5 independent probe: fuzzy edit cost growth, loop stall, and SQLite writer-lock hold."""
import asyncio, sqlite3, threading, time, os
import vfs.storage.replace as R
from vfs import AsyncVirtualFileSystem, InMemoryStorage, DatabaseStorage, Authority, Principal

alice = Authority.of(Principal("alice"))
bob = Authority.of(Principal("bob"))
cells = [0]
_lev = R.levenshtein
def lev(a, b):
    cells[0] += (len(a) + 1) * (len(b) + 1)
    return _lev(a, b)
R.levenshtein = lev
iters = [0]
_strip_calls = [0]

async def ticker(stop, gaps):
    last = time.perf_counter()
    while not stop.is_set():
        await asyncio.sleep(0.002)
        now = time.perf_counter(); gaps.append(now - last); last = now

async def probe(fs, label, path, content, old, lock_db=None):
    w = await fs.write(path=path, content=content, authority=alice)
    assert w.success, w
    stop = asyncio.Event(); gaps = []
    t = asyncio.create_task(ticker(stop, gaps)); await asyncio.sleep(0.02)
    lock = {}
    th = None
    if lock_db:
        def rival():
            time.sleep(0.15)
            c = sqlite3.connect(lock_db, timeout=0)
            try:
                c.execute("BEGIN IMMEDIATE"); lock["rival"] = "acquired"; c.rollback()
            except sqlite3.OperationalError as e:
                lock["rival"] = f"refused: {e}"
            finally:
                c.close()
        th = threading.Thread(target=rival); th.start()
    cells[0] = 0
    s = time.perf_counter()
    r = await fs.edit(path=path, old=old, new="z", authority=alice)
    dt = time.perf_counter() - s
    stop.set(); await t
    if th: th.join()
    after = await fs.read(path=path, authority=alice)
    unchanged = after.success and after.entries[0].content == content if hasattr(after, "entries") else "?"
    kind = r.errors[0].kind if r.errors else None
    print(f"{label:26s} bytes={len(content)+len(old):7d} edit_ms={dt*1e3:8.1f} lev_cells={cells[0]:9d} "
          f"max_gap_ms={max(gaps)*1e3:8.1f} success={r.success} err={kind} unchanged={unchanged} {lock.get('rival','')}")
    return dt

async def run_shapes(fs, tag, lock_db=None):
    print(f"#### {tag}")
    await probe(fs, "control exact L=8000", "/c.txt", "a\n" * 7999 + "q\n", "q", lock_db)
    p = None
    for L in (3000, 6000, 12000):
        d = await probe(fs, f"anchor L={L}", f"/a{L}.txt", "a\n" * L, "a\nx\nb", lock_db)
        if p: print(f"   ratio {d/p:.2f}")
        p = d
    p = None
    for M in (600, 1200, 2400):
        d = await probe(fs, f"lev M={M}", f"/l{M}.txt", "a\n" + "x" * M + "\nb\n", "a\n" + "y" * M + "\nb", lock_db)
        if p: print(f"   ratio {d/p:.2f}")
        p = d
    p = None
    for L in (3000, 6000, 12000):
        d = await probe(fs, f"trim L={L}", f"/t{L}.txt", "a\n" * L, "  a", lock_db)
        if p: print(f"   ratio {d/p:.2f}")
        p = d

async def main():
    fs = AsyncVirtualFileSystem(storage=InMemoryStorage())
    await run_shapes(fs, "InMemoryStorage")
    db = os.path.join(os.getcwd(), "tmp", "f15.db")
    if os.path.exists(db): os.remove(db)
    fs2 = AsyncVirtualFileSystem(storage=DatabaseStorage(url=f"sqlite+aiosqlite:///{db}"))
    await run_shapes(fs2, "file SQLite DatabaseStorage (rival BEGIN IMMEDIATE at +150ms, timeout 0)", db)

asyncio.run(main())
