import asyncio, time, tempfile
from dataclasses import replace
from vfs.models import Entry
from vfs.paths import Path
from vfs.storage.backends.database import DatabaseStorage, dialects
async def writes(url, n=30):
    s=DatabaseStorage(url=url); await s.stat(path=Path("/"))
    t=time.perf_counter()
    for i in range(n): assert (await s.write(entries=[Entry(path=Path(f"/b{i}.txt"), content="y")], parents=True)).success
    e=(time.perf_counter()-t)/n; await s.close(); return e*1000
async def main():
    base=dialects.PROFILES["sqlite"] if isinstance(dialects.PROFILES, dict) else dialects.SQLITE
    def patch(settings):
        new=replace(base, session_settings=settings)
        dialects.SQLITE=new
        if isinstance(dialects.PROFILES, dict): dialects.PROFILES["sqlite"]=new
    for label, settings in (("FULL (as shipped)", base.session_settings), ("NORMAL", tuple("PRAGMA synchronous = NORMAL" if "synchronous" in s else s for s in base.session_settings)), ("OFF", tuple("PRAGMA synchronous = OFF" if "synchronous" in s else s for s in base.session_settings))):
        patch(settings); await writes(f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/vfs.sqlite", 5)
        r=[await writes(f"sqlite+aiosqlite:///{tempfile.mkdtemp()}/vfs.sqlite") for _ in range(3)]
        print(f"file  {label:18} per 1-file write+commit: {sum(r)/3:5.1f} ms   settings={settings}")
    patch(base.session_settings)
    r=[await writes("sqlite+aiosqlite:///:memory:") for _ in range(3)]
    print(f"memory FULL               per 1-file write+commit: {sum(r)/3:5.1f} ms")
asyncio.run(main())
