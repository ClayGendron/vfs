"""The errors behind r3_04b's marked cells."""
import asyncio, sys, sqlite3
from vfs import AsyncVirtualFileSystem, Authority, DatabaseStorage, Principal
DB = sys.argv[1]
async def main():
    fs = AsyncVirtualFileSystem(storage=DatabaseStorage(url=f"sqlite+aiosqlite:///{DB}"))
    for scope, a in [(("/pub",), Authority.anonymous()), (("/.vfs/trash/pub",), Authority.system()), (("/team",), Authority.of(Principal("bob")))]:
        r = await fs.grep("static", paths=scope, authority=a, output_mode="files")
        print(scope, len(r.observations), [(e.kind, e.message[:160]) for e in r.errors])
    raw = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    print(raw.execute("select substr(path,1,12), everyone_level, count(*) from vfs_entries group by 1,2 order by 1").fetchall())
    await fs.close()
asyncio.run(main())
