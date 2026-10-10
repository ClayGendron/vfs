import asyncio, time, tempfile, shutil, pathlib
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage
async def open_write_close(url):
    t=time.perf_counter(); s=DatabaseStorage(url=url)
    r=await s.write(entries=[Entry(path=Path("/a.txt"), content="x")], parents=True); assert r.success, r.errors
    await s.close(); return time.perf_counter()-t
async def main():
    d=pathlib.Path(tempfile.mkdtemp()); tpl=d/"tpl.sqlite"
    s=DatabaseStorage(url=f"sqlite+aiosqlite:///{tpl}"); await s.stat(path=Path("/")); await s.close()
    print("template files:", [p.name for p in d.iterdir()])
    for _ in range(3): await open_write_close(f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/vfs.sqlite")
    fresh=[await open_write_close(f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/vfs.sqlite") for _ in range(10)]
    copied=[]
    for _ in range(10):
        dd=pathlib.Path(tempfile.mkdtemp()); 
        for p in d.iterdir(): shutil.copy(p, dd/p.name.replace("tpl","vfs"))
        copied.append(await open_write_close(f"sqlite+aiosqlite:///{dd}/vfs.sqlite"))
    print(f"fresh file open+write+close  mean {sum(fresh)/10*1000:.1f} ms")
    print(f"copied-template open+write+close mean {sum(copied)/10*1000:.1f} ms")
asyncio.run(main())
